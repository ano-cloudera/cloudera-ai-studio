from __future__ import annotations

import logging
from time import perf_counter
from urllib.parse import quote_plus

from app.connectors.base import ConnectionTestResult, DatasourceConnector, QueryResult
from app.connectors.capabilities import POSTGRES_CAPABILITIES, ConnectorCapabilities
from app.connectors.config import PostgresConnectorConfig
from app.connectors.error_mapping import classify_connection_error
from app.connectors.errors import ConnectorError, UnsupportedOperationError
from app.connectors.identifiers import validate_identifier
from app.connectors.metadata import ColumnInfo, SchemaInfo, TableDetail, TableInfo
from app.connectors.sql_safety import assert_connector_readonly_sql
from app.connectors.type_normalization import normalize_data_type, normalize_table_type

logger = logging.getLogger(__name__)


class PostgresConnector(DatasourceConnector):
    """External PostgreSQL datasource — never uses accelerator DATABASE_URL."""

    connector_type = "postgres"

    def __init__(
        self,
        config: PostgresConnectorConfig,
        *,
        password: str | None = None,
        connect_timeout_seconds: int = 30,
        query_timeout_seconds: int = 60,
        metadata_timeout_seconds: int = 30,
    ) -> None:
        self._config = config
        self._password = password or ""
        self._connect_timeout = connect_timeout_seconds
        self._query_timeout = config.timeout_seconds or query_timeout_seconds
        self._metadata_timeout = metadata_timeout_seconds
        self._dsn = self._build_dsn()

    def _build_dsn(self) -> str:
        user = quote_plus(self._config.username or "postgres")
        host = self._config.host
        port = self._config.port
        db = quote_plus(self._config.database)
        auth = f"{user}:{quote_plus(self._password)}" if self._password else user
        return f"postgresql://{auth}@{host}:{port}/{db}?sslmode={self._config.sslmode}"

    def get_capabilities(self) -> ConnectorCapabilities:
        return POSTGRES_CAPABILITIES

    def default_context(self) -> tuple[str | None, str | None]:
        return None, "public"

    def _connect(self):
        try:
            import psycopg
        except ImportError as exc:
            raise ConnectorError("UNSUPPORTED_OPERATION", "psycopg not installed", 503) from exc
        return psycopg.connect(self._dsn, connect_timeout=self._connect_timeout)

    def _run_query(self, sql: str, params: tuple | list | None = None, *, max_rows: int | None = None) -> list[dict]:
        assert_connector_readonly_sql(sql)
        conn = self._connect()
        timeout_ms = int((self._metadata_timeout if "information_schema" in sql else self._query_timeout) * 1000)
        try:
            with conn.cursor() as cur:
                cur.execute(f"SET statement_timeout = '{timeout_ms}'")
                cur.execute(sql, params or ())
                if cur.description is None:
                    return []
                columns = [d.name for d in cur.description]
                rows = cur.fetchmany(max_rows) if max_rows else cur.fetchall()
                return [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()

    def test_connection(self) -> ConnectionTestResult:
        started = perf_counter()
        phases: dict[str, str] = {}
        try:
            phases["network"] = "PASS"
            conn = self._connect()
            phases["authentication"] = "PASS"
            conn.close()
            phases["session"] = "PASS"
            rows = self._run_query("SELECT 1 AS ok", max_rows=1)
            phases["metadata"] = "PASS"
            latency = round((perf_counter() - started) * 1000, 2)
            version = None
            try:
                ver = self._run_query("SELECT version()", max_rows=1)
                if ver:
                    version = str(next(iter(ver[0].values())))
            except Exception:
                pass
            ok = rows and rows[0].get("ok") == 1
            return ConnectionTestResult(
                status="SUCCESS" if ok else "FAILED",
                latency_ms=latency,
                message="Connection successful" if ok else "Unexpected probe result",
                server_version=version,
                server_name=self._config.host,
                default_schema="public",
                capabilities=self.get_capabilities().to_api_dict(),
                phases=phases,
            )
        except ConnectorError as exc:
            code = exc.code
            return ConnectionTestResult(
                status="FAILED",
                latency_ms=round((perf_counter() - started) * 1000, 2),
                message=exc.message,
                error_code=code,
                phases=phases,
            )
        except Exception as exc:
            code, msg = classify_connection_error(exc)
            logger.info("postgres_connector_test_failed type=%s code=%s", type(exc).__name__, code)
            return ConnectionTestResult(
                status="FAILED",
                latency_ms=round((perf_counter() - started) * 1000, 2),
                message=msg,
                error_code=code,
                phases=phases,
            )

    def list_catalogs(self) -> list:
        raise UnsupportedOperationError("PostgreSQL connector does not expose catalogs")

    def list_schemas(self, *, catalog: str | None = None) -> list[SchemaInfo]:
        rows = self._run_query(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name NOT LIKE 'pg_%%' AND schema_name <> 'information_schema' "
            "ORDER BY 1",
            max_rows=_MAX_LIST,
        )
        return [SchemaInfo(name=str(r["schema_name"])) for r in rows]

    def list_tables(self, *, catalog: str | None = None, schema: str | None = None) -> list[TableInfo]:
        sch = validate_identifier(schema or "public", label="schema")
        rows = self._run_query(
            "SELECT table_name, table_type FROM information_schema.tables "
            f"WHERE table_schema = '{sch}' ORDER BY table_name",
            max_rows=_MAX_LIST,
        )
        tables: list[TableInfo] = []
        for row in rows:
            name = str(row.get("table_name", ""))
            if name:
                tables.append(
                    TableInfo(
                        name=name,
                        schema=sch,
                        table_type=normalize_table_type(str(row.get("table_type", "TABLE"))),
                    )
                )
        return tables

    def describe_table(
        self,
        *,
        catalog: str | None = None,
        schema: str | None = None,
        table: str,
    ) -> list[ColumnInfo]:
        sch = validate_identifier(schema or "public", label="schema")
        tbl = validate_identifier(table, label="table")
        rows = self._run_query(
            "SELECT column_name, data_type, is_nullable, ordinal_position "
            "FROM information_schema.columns "
            f"WHERE table_schema = '{sch}' AND table_name = '{tbl}' "
            "ORDER BY ordinal_position",
            max_rows=_MAX_LIST,
        )
        return [
            ColumnInfo(
                name=str(r["column_name"]),
                data_type=str(r.get("data_type", "")),
                native_type=str(r.get("data_type", "")),
                normalized_type=normalize_data_type(str(r.get("data_type", ""))),
                nullable=str(r.get("is_nullable", "")).upper() == "YES",
                ordinal_position=int(r["ordinal_position"]) if r.get("ordinal_position") else None,
                comment=str(r["comment"]) if r.get("comment") else None,
            )
            for r in rows
        ]

    def enrich_table_detail(self, detail: TableDetail, *, catalog: str | None, schema: str | None, table: str) -> TableDetail:
        sch = validate_identifier(schema or "public", label="schema")
        tbl = validate_identifier(table, label="table")
        pk_rows = self._run_query(
            "SELECT kcu.column_name FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema "
            f"WHERE tc.table_schema = '{sch}' AND tc.table_name = '{tbl}' AND tc.constraint_type = 'PRIMARY KEY' "
            "ORDER BY kcu.ordinal_position",
            max_rows=64,
        )
        detail.primary_key = [str(r["column_name"]) for r in pk_rows] or None
        trows = self._run_query(
            f"SELECT table_type FROM information_schema.tables WHERE table_schema = '{sch}' AND table_name = '{tbl}'",
            max_rows=1,
        )
        if trows:
            detail.table_type = normalize_table_type(str(trows[0].get("table_type", "TABLE")))
        detail.schema = sch
        detail.name = tbl
        return detail

    def execute_readonly_query(self, sql: str, *, max_rows: int) -> QueryResult:
        limited = sql.strip()
        if "limit" not in limited.casefold():
            limited = f"{limited.rstrip(';')} LIMIT {max_rows}"
        rows = self._run_query(limited, max_rows=max_rows)
        columns = list(rows[0].keys()) if rows else []
        return QueryResult(columns=columns, rows=rows, row_count=len(rows))


_MAX_LIST = 10_000
