from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


DataHealthStatus = Literal["ok", "unknown", "unavailable", "auth_required", "auth_failed", "misconfigured", "degraded"]


class BackendColumn(BaseModel):
    name: str
    type: str


class QueryTelemetry(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    data_backend: str
    catalog: str | None = None
    schema_name: str | None = Field(default=None, alias="schema")
    query_latency_ms: float = Field(ge=0)
    row_count: int = Field(ge=0)
    success: bool
    safe_error_code: str | None = None

    @property
    def schema(self) -> str | None:
        return self.schema_name


class BackendQueryResult(BaseModel):
    columns: list[BackendColumn]
    rows: list[list[Any]]
    row_count: int
    telemetry: QueryTelemetry

    def records(self) -> list[dict[str, Any]]:
        names = [column.name for column in self.columns]
        return [dict(zip(names, row)) for row in self.rows]


class DataBackendHealth(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    type: str
    status: DataHealthStatus
    catalog: str | None = None
    schema_name: str | None = Field(default=None, alias="schema")

    @property
    def schema(self) -> str | None:
        return self.schema_name


class BackendExecutionContext(BaseModel):
    trace_id: str = ""
    purpose: str = "analytics"


class DataBackendError(RuntimeError):
    """Safe application-facing data error. Driver messages stay inside adapters."""

    def __init__(self, code: str, telemetry: QueryTelemetry | None = None):
        self.code = code
        self.telemetry = telemetry
        super().__init__(code)


class DataBackend(Protocol):
    dialect: str

    def execute(self, query: str, context: BackendExecutionContext | None = None) -> BackendQueryResult: ...

    def health_check(self, probe: bool = False) -> DataBackendHealth: ...

    def close(self) -> None: ...


def normalize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return str(value)
