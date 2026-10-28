from __future__ import annotations

import logging
from time import perf_counter

from app.connectors.base import ConnectionTestResult, DatasourceConnector, QueryResult
from app.connectors.capabilities import TRINO_CAPABILITIES, ConnectorCapabilities
from app.connectors.config import TrinoConnectorConfig
from app.connectors.error_mapping import classify_connection_error
from app.connectors.errors import ConnectorError, UnsupportedOperationError
from app.connectors.identifiers import quote_trino, validate_identifier
from app.connectors.metadata import CatalogInfo, ColumnInfo, SchemaInfo, TableInfo
from app.connectors.sql_safety import assert_connector_readonly_sql
from app.connectors.type_normalization import normalize_data_type

logger = logging.getLogger(__name__)


class TrinoConnector(DatasourceConnector):
    connector_type = "trino"

    def __init__(
        self,
        config: TrinoConnectorConfig,
        *,
        password: str | None = None,
        query_timeout_seconds: int = 60,
    ) -> None:
        self._config = config
        self._password = password
        self._query_timeout = config.timeout_seconds or query_timeout_seconds

    def get_capabilities(self) -> ConnectorCapabilities:
        return TRINO_CAPABILITIES

    def default_context(self) -> tuple[str | None, str | None]:
        return self._config.catalog or None, self._config.schema

    def _connect(self, *, catalog: str | None = None, schema: str | None = None):
        try:
            import trino
        except ImportError as exc:
            raise ConnectorError("UNSUPPORTED_OPERATION", "Trino client not installed", 503) from exc
        auth = None
        if self._config.auth_type in {"plain", "ldap"} and self._password:
            auth = trino.auth.BasicAuthentication(self._config.username or "trino", self._password)
        return trino.dbapi.connect(
            host=self._config.host,
            port=self._config.port,
            user=self._config.username or "trino",
            catalog=catalog or self._config.catalog or None,
            schema=schema or self._config.schema,
            http_scheme=self._config.http_scheme,
            auth=auth,
        )

    def _run_query(
        self,
        sql: str,
        *,
        catalog: str | None = None,
        schema: str | None = None,
        max_rows: int | None = None,
        metadata: bool = False,
    ) -> list[dict]:
        # SHOW/DESCRIBE are read-only but the shared SQL guard only admits SELECT; the connector builds
        # these itself from validated identifiers, so they skip the guard.
        if not metadata:
            assert_connector_readonly_sql(sql)
        conn = self._connect(catalog=catalog, schema=schema)
        cur = conn.cursor()
        try:
            cur.execute(sql)
            if cur.description is None:
                return []
            columns = [d[0] for d in cur.description]
            rows = cur.fetchmany(max_rows) if max_rows else cur.fetchall()
            return [dict(zip(columns, row)) for row in rows]
        finally:
            cur.close()
            conn.close()

    def test_connection(self) -> ConnectionTestResult:
        started = perf_counter()
        phases: dict[str, str] = {}
        try:
            phases["network"] = "PASS"
            self._connect().close()
            phases["authentication"] = "PASS"
            rows = self._run_query("SELECT 1 AS ok", max_rows=1)
            phases["session"] = "PASS"
            phases["metadata"] = "PASS"
            latency = round((perf_counter() - started) * 1000, 2)
            version = None
            try:
                ver = self._run_query("SELECT version()", max_rows=1)
                if ver:
                    version = str(next(iter(ver[0].values())))
            except Exception:
                pass
            ok = bool(rows)
            return ConnectionTestResult(
                status="SUCCESS" if ok else "FAILED",
                latency_ms=latency,
                message="Connection successful" if ok else "Unexpected probe result",
                server_version=version,
                server_name=self._config.host,
                default_catalog=self._config.catalog or None,
                default_schema=self._config.schema,
                capabilities=self.get_capabilities().to_api_dict(),
                phases=phases,
            )
        except ConnectorError as exc:
            return ConnectionTestResult(
                status="FAILED",
                latency_ms=round((perf_counter() - started) * 1000, 2),
                message=exc.message,
                error_code=exc.code,
                phases=phases,
            )
        except Exception as exc:
            code, msg = classify_connection_error(exc)
            logger.info("trino_connector_test_failed type=%s code=%s", type(exc).__name__, code)
            return ConnectionTestResult(
                status="FAILED",
                latency_ms=round((perf_counter() - started) * 1000, 2),
                message=msg,
                error_code=code,
                phases=phases,
            )

    def list_catalogs(self) -> list[CatalogInfo]:
        rows = self._run_query("SHOW CATALOGS", max_rows=10_000, metadata=True)
        return [CatalogInfo(name=str(next(iter(r.values())))) for r in rows if r]

    def list_schemas(self, *, catalog: str | None = None) -> list[SchemaInfo]:
        cat = validate_identifier(catalog or self._config.catalog or "", label="catalog")
        if not cat:
            raise ConnectorError("CATALOG_NOT_FOUND", "Catalog is required for Trino schema listing", 400)
        rows = self._run_query(f"SHOW SCHEMAS FROM {quote_trino(cat)}", catalog=cat, max_rows=10_000, metadata=True)
        return [SchemaInfo(name=str(next(iter(r.values()))), catalog=cat) for r in rows if r]

    def list_tables(self, *, catalog: str | None = None, schema: str | None = None) -> list[TableInfo]:
        cat = validate_identifier(catalog or self._config.catalog or "", label="catalog")
        sch = validate_identifier(schema or self._config.schema or "", label="schema")
        if not cat or not sch:
            raise ConnectorError("SCHEMA_NOT_FOUND", "Catalog and schema are required", 400)
        rows = self._run_query(
            f"SHOW TABLES FROM {quote_trino(cat)}.{quote_trino(sch)}",
            catalog=cat,
            schema=sch,
            max_rows=10_000,
            metadata=True,
        )
        return [
            TableInfo(name=str(next(iter(r.values()))), schema=sch, catalog=cat, table_type="TABLE")
            for r in rows
            if r
        ]

    def describe_table(
        self,
        *,
        catalog: str | None = None,
        schema: str | None = None,
        table: str,
    ) -> list[ColumnInfo]:
        cat = validate_identifier(catalog or self._config.catalog or "", label="catalog")
        sch = validate_identifier(schema or self._config.schema or "", label="schema")
        tbl = validate_identifier(table, label="table")
        qual = f"{quote_trino(cat)}.{quote_trino(sch)}.{quote_trino(tbl)}"
        rows = self._run_query(f"DESCRIBE {qual}", catalog=cat, schema=sch, max_rows=10_000, metadata=True)
        cols: list[ColumnInfo] = []
        for idx, row in enumerate(rows):
            name = row.get("Column") or row.get("column") or next(iter(row.values()), "")
            dtype = row.get("Type") or row.get("type") or ""
            if name:
                native = str(dtype)
                cols.append(
                    ColumnInfo(
                        name=str(name),
                        data_type=native,
                        native_type=native,
                        normalized_type=normalize_data_type(native),
                        ordinal_position=idx + 1,
                    )
                )
        return cols

    def execute_readonly_query(self, sql: str, *, max_rows: int) -> QueryResult:
        limited = sql.strip()
        if "limit" not in limited.casefold():
            limited = f"{limited.rstrip(';')} LIMIT {max_rows}"
        rows = self._run_query(limited, max_rows=max_rows)
        columns = list(rows[0].keys()) if rows else []
        return QueryResult(columns=columns, rows=rows, row_count=len(rows))
