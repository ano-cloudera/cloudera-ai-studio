from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urljoin

import httpx

from app.ai_registry.adapters.base import AIProviderAdapter
from app.ai_registry.errors import AiRegistryError
from app.ai_registry.secrets import SecretResolver
from app.ai_registry.types import AdapterTestResult


class OpenAICompatibleAdapter(AIProviderAdapter):
    provider_type = "OPENAI_COMPATIBLE"

    def __init__(
        self,
        *,
        base_url: str,
        secret_ref: str | None,
        config: dict[str, Any] | None,
        secrets: SecretResolver | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._secret_ref = secret_ref
        self._config = config or {}
        self._secrets = secrets or SecretResolver()
        self._timeout = timeout
        self._strategy = str(self._config.get("test_strategy") or "AUTO").upper()

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._secret_ref:
            token = self._secrets.resolve(self._secret_ref)
            headers["Authorization"] = f"Bearer {token}"
        extra = self._config.get("headers")
        if isinstance(extra, dict):
            for k, v in extra.items():
                if isinstance(k, str) and isinstance(v, str) and k.lower() != "authorization":
                    headers[k] = v
        return headers

    async def test_connection(self) -> AdapterTestResult:
        started = time.perf_counter()
        if self._strategy in {"MODELS_ENDPOINT", "AUTO"}:
            result = await self._try_models_list(started)
            if result.status == "READY" or self._strategy == "MODELS_ENDPOINT":
                return result
        return await self._chat_smoke(started)

    async def _get_models_response(self) -> httpx.Response:
        url = urljoin(self._base_url + "/", "models")
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.get(url, headers=self._headers())

    @staticmethod
    def _parse_openai_models_payload(payload: Any) -> list[dict[str, Any]]:
        items: list[Any] = []
        if isinstance(payload, dict):
            raw = payload.get("data")
            if isinstance(raw, list):
                items = raw
        elif isinstance(payload, list):
            items = payload
        models: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            model_id = item.get("id")
            if not isinstance(model_id, str) or not model_id.strip():
                continue
            display = item.get("name") if isinstance(item.get("name"), str) else model_id
            models.append({"id": model_id, "display_name": display})
        models.sort(key=lambda row: row["id"].lower())
        return models

    async def list_models(self) -> list[dict[str, Any]]:
        try:
            resp = await self._get_models_response()
        except httpx.TimeoutException as exc:
            raise AiRegistryError("TEST_TIMEOUT", "The provider did not respond in time.", 504) from exc
        except httpx.HTTPError as exc:
            raise AiRegistryError("PROVIDER_UNREACHABLE", "Could not reach the provider endpoint.", 502) from exc
        if resp.status_code in (401, 403):
            raise AiRegistryError("AUTHENTICATION_FAILED", "Authentication was rejected by the provider.", 401)
        if resp.status_code >= 400:
            raise AiRegistryError("PROVIDER_UNREACHABLE", "The provider models endpoint returned an error.", 502)
        try:
            payload = resp.json()
        except json.JSONDecodeError as exc:
            raise AiRegistryError("PROVIDER_UNREACHABLE", "The provider returned an invalid models payload.", 502) from exc
        return self._parse_openai_models_payload(payload)

    async def _try_models_list(self, started: float) -> AdapterTestResult:
        try:
            resp = await self._get_models_response()
            latency = round((time.perf_counter() - started) * 1000, 2)
            if resp.status_code == 401 or resp.status_code == 403:
                return AdapterTestResult(
                    status="FAILED",
                    latency_ms=latency,
                    error_code="AUTHENTICATION_FAILED",
                    safe_message="Authentication was rejected by the provider.",
                )
            if resp.status_code >= 400:
                return AdapterTestResult(
                    status="FAILED",
                    latency_ms=latency,
                    error_code="PROVIDER_UNREACHABLE",
                    safe_message="The provider models endpoint returned an error.",
                )
            return AdapterTestResult(
                status="READY",
                latency_ms=latency,
                metadata={"endpoint": "models"},
            )
        except httpx.TimeoutException:
            return AdapterTestResult(
                status="FAILED",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                error_code="TEST_TIMEOUT",
                safe_message="The provider did not respond in time.",
            )
        except httpx.HTTPError:
            return AdapterTestResult(
                status="FAILED",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                error_code="PROVIDER_UNREACHABLE",
                safe_message="Could not reach the provider endpoint.",
            )

    async def _chat_smoke(self, started: float) -> AdapterTestResult:
        model_id = str(self._config.get("smoke_model_id") or "gpt-3.5-turbo")
        url = urljoin(self._base_url + "/", "chat/completions")
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": "Reply with OK."}],
            "max_tokens": 5,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, headers={**self._headers(), "Content-Type": "application/json"}, json=payload)
            latency = round((time.perf_counter() - started) * 1000, 2)
            if resp.status_code in (401, 403):
                return AdapterTestResult(
                    status="FAILED",
                    latency_ms=latency,
                    error_code="AUTHENTICATION_FAILED",
                    safe_message="Authentication was rejected by the provider.",
                )
            if resp.status_code >= 400:
                return AdapterTestResult(
                    status="FAILED",
                    latency_ms=latency,
                    error_code="MODEL_INVALID",
                    safe_message="Chat smoke validation failed against the provider.",
                )
            return AdapterTestResult(status="READY", latency_ms=latency, metadata={"endpoint": "chat/completions"})
        except httpx.TimeoutException:
            return AdapterTestResult(
                status="FAILED",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                error_code="TEST_TIMEOUT",
                safe_message="The provider did not respond in time.",
            )
        except httpx.HTTPError:
            return AdapterTestResult(
                status="FAILED",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                error_code="PROVIDER_UNREACHABLE",
                safe_message="Could not reach the provider endpoint.",
            )

    async def validate_model(self, *, model_id: str, model_type: str) -> AdapterTestResult:
        if model_type != "CHAT":
            return AdapterTestResult(
                status="FAILED",
                latency_ms=0.0,
                error_code="INVALID_ASSIGNMENT",
                safe_message="OpenAI-compatible chat validation supports CHAT models only in this phase.",
            )
        started = time.perf_counter()
        url = urljoin(self._base_url + "/", "chat/completions")
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": "Reply with OK."}],
            "max_tokens": 5,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, headers={**self._headers(), "Content-Type": "application/json"}, json=payload)
            latency = round((time.perf_counter() - started) * 1000, 2)
            if resp.status_code in (401, 403):
                return AdapterTestResult(
                    status="FAILED",
                    latency_ms=latency,
                    error_code="AUTHENTICATION_FAILED",
                    safe_message="Authentication was rejected by the provider.",
                )
            if resp.status_code >= 400:
                return AdapterTestResult(
                    status="FAILED",
                    latency_ms=latency,
                    error_code="MODEL_INVALID",
                    safe_message="The selected model could not be validated.",
                )
            return AdapterTestResult(status="READY", latency_ms=latency, metadata={"model_id": model_id})
        except httpx.TimeoutException:
            return AdapterTestResult(
                status="FAILED",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                error_code="TEST_TIMEOUT",
                safe_message="Model validation timed out.",
            )
        except httpx.HTTPError:
            return AdapterTestResult(
                status="FAILED",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                error_code="PROVIDER_UNREACHABLE",
                safe_message="Could not reach the provider during model validation.",
            )
