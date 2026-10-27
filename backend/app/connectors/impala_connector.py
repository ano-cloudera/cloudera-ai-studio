from __future__ import annotations

import logging
from time import perf_counter

from app.connectors.base import ConnectionTestResult, DatasourceConnector, QueryResult
from app.connectors.capabilities import IMPALA_CAPABILITIES, ConnectorCapabilities
from app.connectors.config import ImpalaConnectorConfig
from app.connectors.error_mapping import classify_connection_error
from app.connectors.errors import ConnectorError
from app.connectors.identifiers import quote_hive, validate_identifier
from app.connectors.metadata import ColumnInfo, SchemaInfo, TableInfo
from app.connectors.sql_safety import assert_connector_readonly_sql
from app.connectors.type_normalization import normalize_data_type

logger = logging.getLogger(__name__)


class ImpalaConnector(DatasourceConnector):
    connector_type = "impala"

    def __init__(
        self,
        config: ImpalaConnectorConfig,
        *,
        password: str | None = None,
        connect_timeout_seconds: int = 30,
        query_timeout_seconds: int = 60,
    ) -> None:
        self._config = config
        self._password = password
        self._connect_timeout = connect_timeout_seconds
        self._query_timeout = config.timeout_seconds or query_timeout_seconds

    def get_capabilities(self) -> ConnectorCapabilities:
        caps = IMPALA_CAPABILITIES
        if self._config.auth_type == "gssapi":
            return ConnectorCapabilities(**{**caps.to_dict(), "supports_kerberos": True})
        return caps

    def default_context(self) -> tuple[str | None, str | None]:
        return None, self._config.database

    def _connect(self):
        try:
            from impala.dbapi import connect
        except ImportError as exc:
            raise ConnectorError("UNSUPPORTED_OPERATION", "Impala client not installed", 503) from exc
        auth_map = {"plain": "PLAIN", "ldap": "LDAP", "gssapi": "GSSAPI", "none": "NOSASL"}
        mechanism = auth_map.get(self._config.auth_type, "PLAIN")
        return connect(
            host=self._config.host,
            port=self._config.port,
            database=self._config.database,
            auth_mechanism=mechanism,
            user=self._config.username or None,
            password=self._password or None,
            use_ssl=self._config.ssl,
            use_http_transport=self._config.http_transport,
            http_path=self._config.http_path or None,
            kerberos_service_name=self._config.kerberos_service_name or "impala",
        )

    def _run_query(self, sql: str, *, max_rows: int | None = None) -> list[dict]:
        assert_connector_readonly_sql(sql)
        conn = self._connect()
        cursor = conn.cursor()
        try:
            cursor.execute(sql, configuration={"QUERY_TIMEOUT_S": str(self._query_timeout)})
            if cursor.description is None:
                return []
            columns = [item[0] for item in cursor.description]
            rows = cursor.fetchmany(max_rows) if max_rows else cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]
        finally:
            cursor.close()
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
                ver_rows = self._run_query("SELECT version()", max_rows=1)
                if ver_rows:
                    version = str(next(iter(ver_rows[0].values())))
            except Exception:
                pass
            ok = rows and rows[0].get("ok") == 1
            return ConnectionTestResult(
                status="SUCCESS" if ok else "FAILED",
                latency_ms=latency,
                message="Connection successful" if ok else "Unexpected probe result",
                server_version=version,
                server_name=self._config.host,
                default_schema=self._config.database,
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
            logger.info("impala_connector_test_failed type=%s code=%s", type(exc).__name__, code)
            return ConnectionTestResult(
                status="FAILED",
                latency_ms=round((perf_counter() - started) * 1000, 2),
                message=msg,
                error_code=code,
                phases=phases,
            )

    def list_schemas(self, *, catalog: str | None = None) -> list[SchemaInfo]:
        rows = self._run_query("SHOW DATABASES", max_rows=10_000)
        schemas = [SchemaInfo(name=str(next(iter(r.values())))) for r in rows if r]
        if not schemas:
            return [SchemaInfo(name=self._config.database)]
        return schemas

    def list_tables(self, *, catalog: str | None = None, schema: str | None = None) -> list[TableInfo]:
        db = validate_identifier(schema or catalog or self._config.database, label="schema")
        rows = self._run_query(f"SHOW TABLES IN {quote_hive(db)}", max_rows=10_000)
        tables: list[TableInfo] = []
        for row in rows:
            name = next(iter(row.values()))
            if name:
                tables.append(TableInfo(name=str(name), schema=db, table_type="TABLE"))
        return tables

    def describe_table(
        self,
        *,
        catalog: str | None = None,
        schema: str | None = None,
        table: str,
    ) -> list[ColumnInfo]:
        db = validate_identifier(schema or catalog or self._config.database, label="schema")
        tbl = validate_identifier(table, label="table")
        qual = f"{quote_hive(db)}.{quote_hive(tbl)}"
        rows = self._run_query(f"DESCRIBE {qual}", max_rows=10_000)
        cols: list[ColumnInfo] = []
        for idx, row in enumerate(rows):
            name = row.get("name") or row.get("col_name") or next(iter(row.values()), "")
            dtype = row.get("type") or row.get("data_type") or ""
            if name and not str(name).startswith("#"):
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

