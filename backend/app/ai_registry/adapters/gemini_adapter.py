from __future__ import annotations

import time
from typing import Any

import httpx

from app.ai_registry.adapters.base import AIProviderAdapter
from app.ai_registry.errors import AiRegistryError
from app.ai_registry.secrets import SecretResolver
from app.ai_registry.types import AdapterTestResult


class GeminiAdapter(AIProviderAdapter):
    provider_type = "GEMINI"

    def __init__(
        self,
        *,
        secret_ref: str,
        config: dict[str, Any] | None = None,
        secrets: SecretResolver | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._secret_ref = secret_ref
        self._config = config or {}
        self._secrets = secrets or SecretResolver()
        self._timeout = timeout
        self._api_base = str(self._config.get("api_base") or "https://generativelanguage.googleapis.com/v1beta")

    async def test_connection(self) -> AdapterTestResult:
        started = time.perf_counter()
        key = self._secrets.resolve(self._secret_ref)
        url = f"{self._api_base.rstrip('/')}/models"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, params={"key": key})
            latency = round((time.perf_counter() - started) * 1000, 2)
            if resp.status_code in (401, 403):
                return AdapterTestResult(
                    status="FAILED",
                    latency_ms=latency,
                    error_code="AUTHENTICATION_FAILED",
                    safe_message="Authentication was rejected by Gemini.",
                )
            if resp.status_code >= 400:
                return AdapterTestResult(
                    status="FAILED",
                    latency_ms=latency,
                    error_code="PROVIDER_UNREACHABLE",
                    safe_message="Gemini models listing failed.",
                )
            return AdapterTestResult(status="READY", latency_ms=latency, metadata={"provider_type": "GEMINI"})
        except httpx.TimeoutException:
            return AdapterTestResult(
                status="FAILED",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                error_code="TEST_TIMEOUT",
                safe_message="Gemini did not respond in time.",
            )
        except httpx.HTTPError:
            return AdapterTestResult(
                status="FAILED",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                error_code="PROVIDER_UNREACHABLE",
                safe_message="Could not reach Gemini.",
            )

    async def list_models(self) -> list[dict[str, Any]]:
        key = self._secrets.resolve(self._secret_ref)
        url = f"{self._api_base.rstrip('/')}/models"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, params={"key": key})
        except httpx.TimeoutException as exc:
            raise AiRegistryError("TEST_TIMEOUT", "Gemini did not respond in time.", 504) from exc
        except httpx.HTTPError as exc:
            raise AiRegistryError("PROVIDER_UNREACHABLE", "Could not reach Gemini.", 502) from exc
        if resp.status_code in (401, 403):
            raise AiRegistryError("AUTHENTICATION_FAILED", "Authentication was rejected by Gemini.", 401)
        if resp.status_code >= 400:
            raise AiRegistryError("PROVIDER_UNREACHABLE", "Gemini models listing failed.", 502)
        try:
            payload = resp.json()
        except ValueError as exc:
            raise AiRegistryError("PROVIDER_UNREACHABLE", "Gemini returned an invalid models payload.", 502) from exc
        rows: list[dict[str, Any]] = []
        for item in payload.get("models") or []:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            model_id = name.split("/")[-1]
            display = item.get("displayName") if isinstance(item.get("displayName"), str) else model_id
            rows.append({"id": model_id, "display_name": display})
        rows.sort(key=lambda row: row["id"].lower())
        return rows
