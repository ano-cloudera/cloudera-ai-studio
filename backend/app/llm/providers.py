from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.llm.base import ProviderError, StructuredT
from app.llm.usage_context import record_llm_usage


logger = logging.getLogger(__name__)


def _http_error_code(response: httpx.Response) -> str:
    try:
        payload = response.json()
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        code = error.get("code") if isinstance(error, dict) else None
        return re.sub(r"[^a-zA-Z0-9_.-]", "_", str(code or "unknown"))[:80]
    except (TypeError, ValueError):
        return "unknown"


def _structured_json(text: str) -> Any:
    value = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", value, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        value = fenced.group(1)
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ProviderError("INVALID_STRUCTURED_OUTPUT") from exc


class _OpenAICompatibleProvider:
    provider_name = "openai"

    def __init__(
        self,
        settings: Settings,
        *,
        base_url: str,
        api_key: str,
        model: str,
        verify_ssl: bool,
        modern_openai_parameters: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.verify_ssl = verify_ssl
        self.modern_openai_parameters = modern_openai_parameters
        self.transport = transport

    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[StructuredT],
        *,
        temperature: float,
        max_tokens: int,
    ) -> StructuredT:
        schema = json.dumps(response_model.model_json_schema(), ensure_ascii=False, separators=(",", ":"))
        schema_instruction = (
            "Return exactly one JSON object that validates against this JSON Schema. "
            f"Do not rename fields or add fields outside the schema: {schema}"
        )
        request_messages = [dict(message) for message in messages]
        if request_messages and request_messages[0].get("role") == "system":
            request_messages[0]["content"] += "\n\n" + schema_instruction
        else:
            request_messages.insert(0, {"role": "system", "content": schema_instruction})
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        for attempt in range(2):
            body = {
                "model": self.model,
                "messages": request_messages,
                "response_format": {"type": "json_object"},
            }
            if self.modern_openai_parameters:
                body["max_completion_tokens"] = max_tokens
            else:
                body["temperature"] = temperature
                body["max_tokens"] = max_tokens
            try:
                async with httpx.AsyncClient(
                    timeout=self.settings.llm_request_timeout_seconds,
                    verify=self.verify_ssl,
                    transport=self.transport,
                ) as client:
                    http_response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=body)
                    http_response.raise_for_status()
                    payload = http_response.json()
                content = payload["choices"][0]["message"]["content"]
                usage = payload.get("usage") if isinstance(payload, dict) else None
                if isinstance(usage, dict):
                    record_llm_usage(
                        provider=self.provider_name,
                        prompt_tokens=int(usage.get("prompt_tokens") or 0),
                        completion_tokens=int(usage.get("completion_tokens") or 0),
                    )
                else:
                    record_llm_usage(provider=self.provider_name, prompt_tokens=0, completion_tokens=0)
            except httpx.TimeoutException as exc:
                raise ProviderError("TIMEOUT") from exc
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "llm_http_error provider=%s status=%s error_code=%s endpoint=%s",
                    self.provider_name,
                    exc.response.status_code,
                    _http_error_code(exc.response),
                    exc.request.url.path,
                )
                raise ProviderError("PROVIDER_ERROR") from exc
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
                raise ProviderError("PROVIDER_ERROR") from exc
            try:
                return response_model.model_validate(_structured_json(content))
            except (ProviderError, ValidationError) as exc:
                if attempt == 1:
                    raise ProviderError("INVALID_STRUCTURED_OUTPUT") from exc
                request_messages = [
                    *request_messages,
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": "The previous JSON did not validate. Return only a corrected JSON object matching the exact schema above.",
                    },
                ]
        raise ProviderError("INVALID_STRUCTURED_OUTPUT")


class QwenProvider(_OpenAICompatibleProvider):
    provider_name = "qwen"

    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        super().__init__(
            settings,
            base_url=settings.qwen_base_url,
            api_key=settings.qwen_api_key.get_secret_value(),
            model=settings.qwen_model,
            verify_ssl=settings.qwen_verify_ssl,
            transport=transport,
        )


class OpenAIProvider(_OpenAICompatibleProvider):
    provider_name = "openai"

    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        super().__init__(
            settings,
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key.get_secret_value(),
            model=settings.openai_model,
            verify_ssl=settings.openai_verify_ssl,
            modern_openai_parameters=True,
            transport=transport,
        )


def _gemini_json_schema(response_model: type[StructuredT]) -> dict[str, Any]:
    def scrub(node: Any) -> Any:
        if isinstance(node, dict):
            return {
                key: scrub(value)
                for key, value in node.items()
                # Do not strip JSON Schema "title" or "default" keys — they include
                # ChartSpec.title and field defaults Gemini needs for structured output.
                if key not in {"additionalProperties", "$schema"}
            }
        if isinstance(node, list):
            return [scrub(item) for item in node]
        return node

    return scrub(response_model.model_json_schema())


def _gemini_messages_to_contents(messages: list[dict[str, str]]):
    from google.genai import types

    contents: list[types.Content] = []
    for item in messages:
        role = item.get("role")
        if role == "system":
            continue
        gemini_role = "model" if role == "assistant" else "user"
        contents.append(
            types.Content(
                role=gemini_role,
                parts=[types.Part.from_text(text=str(item.get("content") or ""))],
            )
        )
    return contents


class GeminiProvider:
    """Google Gemini via ``google-genai`` SDK (same as backend-test)."""

    provider_name = "gemini"

    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self.transport = transport
        self._client: Any = None

    def _client_instance(self):
        if self._client is not None:
            return self._client
        from google import genai

        api_key = self.settings.gemini_api_key.get_secret_value()
        self._client = genai.Client(api_key=api_key) if api_key else genai.Client()
        return self._client

    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[StructuredT],
        *,
        temperature: float,
        max_tokens: int,
    ) -> StructuredT:
        from google.genai import types

        system_instruction = "\n\n".join(
            str(item.get("content") or "") for item in messages if item.get("role") == "system"
        ).strip()
        contents = _gemini_messages_to_contents(messages)
        if not contents:
            contents = [types.Content(role="user", parts=[types.Part.from_text(text="Proceed.")])]

        config = types.GenerateContentConfig(
            system_instruction=system_instruction or None,
            temperature=temperature,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
            response_json_schema=_gemini_json_schema(response_model),
        )
        try:
            response = await self._client_instance().aio.models.generate_content(
                model=self.settings.gemini_model,
                contents=contents,
                config=config,
            )
            text = (response.text or "").strip()
            if not text:
                raise ProviderError("PROVIDER_ERROR")
            meta = getattr(response, "usage_metadata", None)
            prompt_t = completion_t = 0
            if meta is not None:
                prompt_t = int(getattr(meta, "prompt_token_count", 0) or 0)
                completion_t = int(getattr(meta, "candidates_token_count", 0) or 0)
                if completion_t <= 0:
                    total = int(getattr(meta, "total_token_count", 0) or 0)
                    if total > prompt_t:
                        completion_t = total - prompt_t
            record_llm_usage(provider="gemini", prompt_tokens=prompt_t, completion_tokens=completion_t)
            return response_model.model_validate(_structured_json(text))
        except ProviderError:
            raise
        except ValidationError as exc:
            raise ProviderError("INVALID_STRUCTURED_OUTPUT") from exc
        except TimeoutError as exc:
            raise ProviderError("TIMEOUT") from exc
        except Exception as exc:
            logger.warning(
                "llm_sdk_error provider=gemini model=%s error_type=%s detail=%s",
                self.settings.gemini_model,
                type(exc).__name__,
                str(exc)[:500],
            )
            raise ProviderError("PROVIDER_ERROR") from exc
