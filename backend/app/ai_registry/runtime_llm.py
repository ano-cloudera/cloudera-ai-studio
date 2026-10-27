from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from pydantic import ValidationError

from app.ai_registry.runtime_errors import RegistryRuntimeError
from app.ai_registry.runtime_resolver import RuntimeModelResolution
from app.ai_registry.secrets import SecretResolver
from app.core.config import Settings
from app.db.platform_models import AiProviderRow
from app.llm.base import ProviderError, StructuredT
from app.llm.providers import GeminiProvider, _OpenAICompatibleProvider, _structured_json
from app.llm.usage_context import record_llm_usage

logger = logging.getLogger(__name__)


class _RegistryGeminiProvider(GeminiProvider):
    def __init__(self, settings: Settings, *, model_id: str, api_key: str) -> None:
        super().__init__(settings)
        self._registry_model_id = model_id
        self._registry_api_key = api_key

    def _client_instance(self):
        if self._client is not None:
            return self._client
        from google import genai

        self._client = genai.Client(api_key=self._registry_api_key) if self._registry_api_key else genai.Client()
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

        from app.llm.providers import _gemini_json_schema, _gemini_messages_to_contents

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
                model=self._registry_model_id,
                contents=contents,
                config=config,
            )
            text = (response.text or "").strip()
            if not text:
                raise ProviderError("INVALID_PROVIDER_RESPONSE")
            meta = getattr(response, "usage_metadata", None)
            prompt_t = completion_t = 0
            if meta is not None:
                prompt_t = int(getattr(meta, "prompt_token_count", 0) or 0)
                completion_t = int(getattr(meta, "candidates_token_count", 0) or 0)
            record_llm_usage(provider="gemini", prompt_tokens=prompt_t, completion_tokens=completion_t)
            return response_model.model_validate(_structured_json(text))
        except ProviderError:
            raise
        except ValidationError as exc:
            raise ProviderError("INVALID_STRUCTURED_OUTPUT") from exc
        except TimeoutError as exc:
            raise ProviderError("REQUEST_TIMEOUT") from exc
        except Exception as exc:
            logger.warning("registry_gemini_error error_type=%s", type(exc).__name__)
            raise ProviderError("PROVIDER_UNREACHABLE") from exc


class AnthropicStructuredProvider:
    provider_name = "anthropic"

    def __init__(
        self,
        settings: Settings,
        *,
        base_url: str,
        api_key: str,
        model: str,
        anthropic_version: str = "2023-06-01",
    ) -> None:
        self.settings = settings
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.anthropic_version = anthropic_version

    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[StructuredT],
        *,
        temperature: float,
        max_tokens: int,
    ) -> StructuredT:
        schema = json.dumps(response_model.model_json_schema(), ensure_ascii=False, separators=(",", ":"))
        system = "\n\n".join(str(m.get("content") or "") for m in messages if m.get("role") == "system")
        user_parts = [str(m.get("content") or "") for m in messages if m.get("role") != "system"]
        user_text = "\n\n".join(user_parts).strip() or "Proceed."
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": (system + "\n\nReturn JSON matching schema: " + schema).strip(),
            "messages": [{"role": "user", "content": user_text}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.anthropic_version,
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.llm_request_timeout_seconds) as client:
                resp = await client.post(f"{self.base_url}/v1/messages", headers=headers, json=body)
            if resp.status_code in (401, 403):
                raise ProviderError("AUTHENTICATION_FAILED")
            if resp.status_code == 429:
                raise ProviderError("RATE_LIMITED")
            if resp.status_code >= 400:
                raise ProviderError("PROVIDER_UNREACHABLE")
            payload = resp.json()
            blocks = payload.get("content") if isinstance(payload, dict) else None
            text = ""
            if isinstance(blocks, list):
                for block in blocks:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text += str(block.get("text") or "")
            usage = payload.get("usage") if isinstance(payload, dict) else {}
            record_llm_usage(
                provider="anthropic",
                prompt_tokens=int(usage.get("input_tokens") or 0),
                completion_tokens=int(usage.get("output_tokens") or 0),
            )
            return response_model.model_validate(_structured_json(text))
        except httpx.TimeoutException as exc:
            raise ProviderError("REQUEST_TIMEOUT") from exc
        except ProviderError:
            raise
        except (httpx.HTTPError, ValidationError, KeyError, TypeError, ValueError) as exc:
            raise ProviderError("INVALID_PROVIDER_RESPONSE") from exc


def build_registry_llm_provider(
    *,
    settings: Settings,
    provider_row: AiProviderRow,
    resolution: RuntimeModelResolution,
    secrets: SecretResolver | None = None,
) -> Any:
    resolver = secrets or SecretResolver()
    ptype = provider_row.provider_type.upper()
    model_id = resolution.runtime_model_id or ""
    config: dict[str, Any] = dict(provider_row.config_json or {})

    if ptype == "OPENAI":
        key = resolver.resolve(provider_row.secret_ref or "")
        return _OpenAICompatibleProvider(
            settings,
            base_url=(provider_row.base_url or settings.openai_base_url).rstrip("/"),
            api_key=key,
            model=model_id,
            verify_ssl=settings.openai_verify_ssl,
            modern_openai_parameters=True,
            transport=None,
        )

    if ptype == "OPENAI_COMPATIBLE":
        if not provider_row.base_url:
            raise RegistryRuntimeError("PROVIDER_UNREACHABLE", "OpenAI-compatible provider missing base_url", 503)
        key = resolver.resolve(provider_row.secret_ref) if provider_row.secret_ref else ""
        return _OpenAICompatibleProvider(
            settings,
            base_url=provider_row.base_url.rstrip("/"),
            api_key=key,
            model=model_id,
            verify_ssl=bool(config.get("verify_ssl", settings.qwen_verify_ssl)),
            modern_openai_parameters=bool(config.get("modern_openai_parameters", False)),
            transport=None,
        )

    if ptype == "GEMINI":
        key = resolver.resolve(provider_row.secret_ref or "")
        return _RegistryGeminiProvider(settings, model_id=model_id, api_key=key)

    if ptype == "ANTHROPIC":
        key = resolver.resolve(provider_row.secret_ref or "")
        return AnthropicStructuredProvider(
            settings,
            base_url=provider_row.base_url or "https://api.anthropic.com",
            api_key=key,
            model=model_id,
            anthropic_version=str(config.get("anthropic_version") or "2023-06-01"),
        )

    raise RegistryRuntimeError("PROVIDER_UNREACHABLE", f"Unsupported provider_type: {ptype}", 503)


def map_provider_error(exc: Exception) -> RegistryRuntimeError:
    if isinstance(exc, RegistryRuntimeError):
        return exc
    if isinstance(exc, ProviderError):
        code = getattr(exc, "code", "PROVIDER_UNREACHABLE")
        mapping = {
            "TIMEOUT": "REQUEST_TIMEOUT",
            "PROVIDER_ERROR": "PROVIDER_UNREACHABLE",
        }
        return RegistryRuntimeError(mapping.get(code, code), str(exc), 503)
    return RegistryRuntimeError("PROVIDER_UNREACHABLE", "Model provider request failed", 503)
