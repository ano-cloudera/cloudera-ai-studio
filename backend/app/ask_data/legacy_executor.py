from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import Settings
from app.db.base import BackendExecutionContext
from app.db.duckdb_governed_backend import DuckDBGovernedBackend
from app.db.impala_backend import ImpalaBackend


class ImpalaQueryExecutor:
    def __init__(self, settings: Settings) -> None:
        self.backend = ImpalaBackend(settings)

    async def execute(self, sql: str, state: dict[str, Any] | str) -> dict[str, Any]:
        request_id = state if isinstance(state, str) else str(state.get("request_id") or "")
        result = await asyncio.to_thread(
            self.backend.execute,
            sql,
            BackendExecutionContext(trace_id=request_id, purpose="ask_data_v2"),
        )
        return {
            "columns": [column.name for column in result.columns],
            "rows": result.records(),
            "row_count": result.row_count,
            "execution_ms": result.telemetry.query_latency_ms,
        }


class DuckDBQueryExecutor:
    def __init__(self, settings: Settings) -> None:
        self.backend = DuckDBGovernedBackend(settings)

    async def execute(self, sql: str, state: dict[str, Any] | str) -> dict[str, Any]:
        request_id = state if isinstance(state, str) else str(state.get("request_id") or "")
        result = await asyncio.to_thread(
            self.backend.execute,
            sql,
            BackendExecutionContext(trace_id=request_id, purpose="ask_data_v2"),
        )
        return {
            "columns": [column.name for column in result.columns],
            "rows": result.records(),
            "row_count": result.row_count,
            "execution_ms": result.telemetry.query_latency_ms,
        }


def build_query_executor(settings: Settings) -> ImpalaQueryExecutor | DuckDBQueryExecutor:
    if settings.data_backend.strip().lower() == "duckdb":
        return DuckDBQueryExecutor(settings)
    return ImpalaQueryExecutor(settings)
