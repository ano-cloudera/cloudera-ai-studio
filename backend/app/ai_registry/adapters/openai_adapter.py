from __future__ import annotations

import time
from typing import Any

import httpx

from app.ai_registry.adapters.openai_compatible import OpenAICompatibleAdapter
from app.ai_registry.secrets import SecretResolver
from app.ai_registry.types import AdapterTestResult


class OpenAIAdapter(OpenAICompatibleAdapter):
    provider_type = "OPENAI"

    def __init__(
        self,
        *,
        secret_ref: str,
        base_url: str | None = None,
        config: dict[str, Any] | None = None,
        secrets: SecretResolver | None = None,
    ) -> None:
        root = (base_url or "https://api.openai.com/v1").rstrip("/")
        super().__init__(base_url=root, secret_ref=secret_ref, config={**(config or {}), "test_strategy": "MODELS_ENDPOINT"}, secrets=secrets)

    async def test_connection(self) -> AdapterTestResult:
        return await self._try_models_list(time.perf_counter())
