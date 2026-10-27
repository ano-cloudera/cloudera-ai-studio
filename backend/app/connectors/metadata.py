from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CatalogInfo:
    name: str
    comment: str | None = None


@dataclass(frozen=True)
class SchemaInfo:
    name: str
    catalog: str | None = None
    comment: str | None = None


@dataclass(frozen=True)
class TableInfo:
    name: str
    schema: str | None = None
    catalog: str | None = None
    table_type: str = "TABLE"
    comment: str | None = None

    @property
    def type(self) -> str:
        return self.table_type.casefold()


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str = ""
    native_type: str = ""
    normalized_type: str = "UNKNOWN"
    nullable: bool | None = None
    comment: str | None = None
    ordinal_position: int | None = None


@dataclass
class TableDetail:
    catalog: str | None
    schema: str | None
    name: str
    table_type: str
    columns: list[ColumnInfo] = field(default_factory=list)
    primary_key: list[str] | None = None
    comment: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SamplePreview:
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
    query_duration_ms: float
    resolved_catalog: str | None = None
    resolved_schema: str | None = None
    resolved_table: str | None = None
