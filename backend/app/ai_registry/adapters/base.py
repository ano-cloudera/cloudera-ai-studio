from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.ai_registry.types import AdapterTestResult


class AIProviderAdapter(ABC):
    provider_type: str

    @abstractmethod
    async def test_connection(self) -> AdapterTestResult:
        ...

    async def validate_model(self, *, model_id: str, model_type: str) -> AdapterTestResult:
        return AdapterTestResult(status="READY", latency_ms=0.0, metadata={"model_id": model_id, "model_type": model_type})

    async def list_models(self) -> list[dict[str, Any]]:
        return []
