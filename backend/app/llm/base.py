from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel


StructuredT = TypeVar("StructuredT", bound=BaseModel)


class LLMProvider(Protocol):
    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[StructuredT],
        *,
        temperature: float,
        max_tokens: int,
    ) -> StructuredT: ...


class ProviderError(RuntimeError):
    def __init__(self, code: str, message: str = "Model provider request failed") -> None:
        self.code = code
        super().__init__(message)
