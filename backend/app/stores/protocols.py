"""Persistence store protocols (M1 platform foundation)."""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from app.core.models import AnalysisOutput, ChartSpec

GroupBy = Literal["day", "model"]


@runtime_checkable
class ConversationStoreProtocol(Protocol):
    def append(
        self,
        session_id: str,
        question: str,
        answer: AnalysisOutput,
        rows: list[dict],
        chart: ChartSpec | None,
        provider: str,
        model: str,
        *,
        status: str = "",
        strategy: str = "",
        session_frame: dict | None = None,
    ) -> None: ...

    def load(self, session_id: str, limit: int = 20) -> list[dict]: ...

    def delete_session(self, session_id: str) -> int: ...


@runtime_checkable
class UsageStoreProtocol(Protocol):
    def record(
        self,
        *,
        request_id: str,
        session_id: str,
        provider: str,
        model: str,
        strategy: str,
        status: str,
        prompt_tokens: int,
        completion_tokens: int,
        llm_calls: int,
    ) -> None: ...

    def totals(self, *, days: int | None = 7, mtd: bool = False) -> dict[str, int]: ...

    def daily_totals(self, *, days: int = 7) -> list[dict[str, Any]]: ...

    def by_model(self, *, days: int = 7) -> list[dict[str, Any]]: ...

    def list_events(self, *, days: int = 7, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]: ...

    def export_csv(self, *, days: int = 30) -> str: ...
