"""Per-request LLM usage accumulation (safe across LangGraph nodes)."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any

from app.llm.base import LLMProvider, StructuredT


@dataclass
class LlmUsageAccumulator:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_calls: int = 0
    providers: list[str] = field(default_factory=list)

    def add(self, *, prompt: int, completion: int, provider: str) -> None:
        self.prompt_tokens += max(0, int(prompt))
        self.completion_tokens += max(0, int(completion))
        self.llm_calls += 1
        if provider and (not self.providers or self.providers[-1] != provider):
            self.providers.append(provider)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class UsageTracker:
    def __init__(self) -> None:
        self._by_request: dict[str, LlmUsageAccumulator] = {}

    def start(self, request_id: str) -> None:
        self._by_request[request_id] = LlmUsageAccumulator()

    def finish(self, request_id: str) -> LlmUsageAccumulator | None:
        return self._by_request.pop(request_id, None)

    def record(self, request_id: str, *, provider: str, prompt_tokens: int, completion_tokens: int) -> None:
        acc = self._by_request.get(request_id)
        if acc is None:
            return
        acc.add(prompt=prompt_tokens, completion=completion_tokens, provider=provider)

    def wrap(self, provider: LLMProvider, request_id: str) -> LLMProvider:
        return _UsageTrackingProvider(provider, self, request_id)


class _UsageTrackingProvider:
    def __init__(self, inner: LLMProvider, tracker: UsageTracker, request_id: str) -> None:
        self._inner = inner
        self._tracker = tracker
        self._request_id = request_id
        self.provider_name = getattr(inner, "provider_name", "unknown")

    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[StructuredT],
        *,
        temperature: float,
        max_tokens: int,
    ) -> StructuredT:
        token = _bind_request(self._request_id)
        try:
            return await self._inner.generate_structured(
                messages,
                response_model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        finally:
            _unbind_request(token)


_active_request_id: ContextVar[str | None] = ContextVar("active_usage_request_id", default=None)
_tracker: ContextVar[UsageTracker | None] = ContextVar("usage_tracker", default=None)


def attach_usage_tracker(tracker: UsageTracker) -> None:
    _tracker.set(tracker)


def start_request_usage(request_id: str) -> None:
    tracker = _tracker.get()
    if tracker is not None:
        tracker.start(request_id)
    _bind_request(request_id)


def finish_request_usage(request_id: str) -> LlmUsageAccumulator | None:
    _active_request_id.set(None)
    tracker = _tracker.get()
    if tracker is None:
        return None
    return tracker.finish(request_id)


def _bind_request(request_id: str) -> Token:
    return _active_request_id.set(request_id)


def _unbind_request(token: Token) -> None:
    _active_request_id.reset(token)


def record_llm_usage(*, provider: str, prompt_tokens: int, completion_tokens: int) -> None:
    request_id = _active_request_id.get()
    tracker = _tracker.get()
    if not request_id or tracker is None:
        return
    tracker.record(
        request_id,
        provider=provider,
        prompt_tokens=int(prompt_tokens),
        completion_tokens=int(completion_tokens),
    )
