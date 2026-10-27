from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.connectors.capabilities import ConnectorCapabilities
from app.connectors.errors import UnsupportedOperationError
from app.connectors.metadata import CatalogInfo, ColumnInfo, SchemaInfo, TableInfo  # noqa: TC001


@dataclass
class ConnectionTestResult:
    status: str
    latency_ms: float
    message: str
    server_version: str | None = None
    server_name: str | None = None
    default_catalog: str | None = None
    default_schema: str | None = None
    capabilities: dict | None = None
    phases: dict[str, str] | None = None
    error_code: str | None = None


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int


class DatasourceConnector(ABC):
    connector_type: str

    @abstractmethod
    def get_capabilities(self) -> ConnectorCapabilities:
        ...

    @abstractmethod
    def test_connection(self) -> ConnectionTestResult:
        ...

    def list_catalogs(self) -> list[CatalogInfo]:
        raise UnsupportedOperationError()

    @abstractmethod
    def list_schemas(self, *, catalog: str | None = None) -> list[SchemaInfo]:
        ...

    @abstractmethod
    def list_tables(self, *, catalog: str | None = None, schema: str | None = None) -> list[TableInfo]:
        ...

    @abstractmethod
    def describe_table(
        self,
        *,
        catalog: str | None = None,
        schema: str | None = None,
        table: str,
    ) -> list[ColumnInfo]:
        ...

    def describe_table_detail(
        self,
        *,
        catalog: str | None = None,
        schema: str | None = None,
        table: str,
    ):
        from app.connectors.metadata import TableDetail
        from app.connectors.type_normalization import normalize_data_type

        columns = self.describe_table(catalog=catalog, schema=schema, table=table)
        enriched = []
        for col in columns:
            native = col.native_type or col.data_type
            enriched.append(
                ColumnInfo(
                    name=col.name,
                    data_type=col.data_type,
                    native_type=native,
                    normalized_type=normalize_data_type(native),
                    nullable=col.nullable,
                    comment=col.comment,
                    ordinal_position=col.ordinal_position,
                )
            )
        return TableDetail(
            catalog=catalog,
            schema=schema,
            name=table,
            table_type="TABLE",
            columns=enriched,
        )

    def default_context(self) -> tuple[str | None, str | None]:
        return None, None

    @abstractmethod
    def execute_readonly_query(self, sql: str, *, max_rows: int) -> QueryResult:
        ...
