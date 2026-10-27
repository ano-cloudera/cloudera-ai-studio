from __future__ import annotations

import time
from typing import Any

import httpx

from app.ai_registry.adapters.base import AIProviderAdapter
from app.ai_registry.errors import AiRegistryError
from app.ai_registry.secrets import SecretResolver
from app.ai_registry.types import AdapterTestResult


class AnthropicAdapter(AIProviderAdapter):
    provider_type = "ANTHROPIC"

    def __init__(
        self,
        *,
        secret_ref: str,
        base_url: str | None = None,
        config: dict[str, Any] | None = None,
        secrets: SecretResolver | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._secret_ref = secret_ref
        self._base_url = (base_url or "https://api.anthropic.com").rstrip("/")
        self._config = config or {}
        self._secrets = secrets or SecretResolver()
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        token = self._secrets.resolve(self._secret_ref)
        version = str(self._config.get("anthropic_version") or "2023-06-01")
        return {
            "x-api-key": token,
            "anthropic-version": version,
            "Accept": "application/json",
        }

    async def test_connection(self) -> AdapterTestResult:
        started = time.perf_counter()
        url = f"{self._base_url}/v1/models"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, headers=self._headers())
            latency = round((time.perf_counter() - started) * 1000, 2)
            if resp.status_code in (401, 403):
                return AdapterTestResult(
                    status="FAILED",
                    latency_ms=latency,
                    error_code="AUTHENTICATION_FAILED",
                    safe_message="Authentication was rejected by Anthropic.",
                )
            if resp.status_code >= 400:
                return AdapterTestResult(
                    status="FAILED",
                    latency_ms=latency,
                    error_code="PROVIDER_UNREACHABLE",
                    safe_message="Anthropic models endpoint returned an error.",
                )
            return AdapterTestResult(status="READY", latency_ms=latency, metadata={"provider_type": "ANTHROPIC"})
        except httpx.TimeoutException:
            return AdapterTestResult(
                status="FAILED",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                error_code="TEST_TIMEOUT",
                safe_message="Anthropic did not respond in time.",
            )
        except httpx.HTTPError:
            return AdapterTestResult(
                status="FAILED",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                error_code="PROVIDER_UNREACHABLE",
                safe_message="Could not reach Anthropic.",
            )

    async def list_models(self) -> list[dict[str, Any]]:
        url = f"{self._base_url}/v1/models"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise AiRegistryError("TEST_TIMEOUT", "Anthropic did not respond in time.", 504) from exc
        except httpx.HTTPError as exc:
            raise AiRegistryError("PROVIDER_UNREACHABLE", "Could not reach Anthropic.", 502) from exc
        if resp.status_code in (401, 403):
            raise AiRegistryError("AUTHENTICATION_FAILED", "Authentication was rejected by Anthropic.", 401)
        if resp.status_code >= 400:
            raise AiRegistryError("PROVIDER_UNREACHABLE", "Anthropic models endpoint returned an error.", 502)
        try:
            payload = resp.json()
        except ValueError as exc:
            raise AiRegistryError("PROVIDER_UNREACHABLE", "Anthropic returned an invalid models payload.", 502) from exc
        rows: list[dict[str, Any]] = []
        for item in payload.get("data") or []:
            if not isinstance(item, dict):
                continue
            model_id = item.get("id")
            if not isinstance(model_id, str) or not model_id.strip():
                continue
            display = item.get("display_name") if isinstance(item.get("display_name"), str) else model_id
            rows.append({"id": model_id, "display_name": display})
        rows.sort(key=lambda row: row["id"].lower())
        return rows
