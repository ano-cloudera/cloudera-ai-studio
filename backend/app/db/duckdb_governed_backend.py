from __future__ import annotations

import logging
from pathlib import Path
from time import perf_counter

import sqlglot

from app.core.config import Settings, get_settings
from app.db.base import BackendColumn, BackendExecutionContext, BackendQueryResult, DataBackendError, DataBackendHealth, QueryTelemetry, normalize_value


logger = logging.getLogger(__name__)


def is_duckdb_governed_configured(settings: Settings) -> bool:
    if settings.data_backend.strip().lower() != "duckdb":
        return False
    path = Path(settings.duckdb_path)
    return path.is_file()


def _to_duckdb_sql(sql: str) -> str:
    try:
        return sqlglot.transpile(sql, read="hive", write="duckdb")[0]
    except Exception:
        return sql


class DuckDBGovernedBackend:
    dialect = "duckdb"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.path = Path(self.settings.duckdb_path)

    def health(self) -> tuple[str, str]:
        configured = is_duckdb_governed_configured(self.settings)
        return ("configured" if configured else "degraded", "duckdb")

    def health_check(self, probe: bool = False) -> DataBackendHealth:
        configured = is_duckdb_governed_configured(self.settings)
        return DataBackendHealth(type="duckdb", status="unknown" if configured else "misconfigured")

    def query(self, sql: str) -> list[dict]:
        try:
            import duckdb
        except ImportError as exc:
            raise RuntimeError("duckdb is not installed. pip install duckdb") from exc

        if not self.path.is_file():
            raise FileNotFoundError(f"Local DuckDB file not found: {self.path}")

        duck_sql = _to_duckdb_sql(sql)
        con = duckdb.connect(str(self.path), read_only=True)
        try:
            cursor = con.execute(duck_sql)
            columns = [item[0] for item in (cursor.description or [])]
            rows = cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]
        finally:
            con.close()

    def execute(self, sql: str, context: BackendExecutionContext | None = None) -> BackendQueryResult:
        context = context or BackendExecutionContext()
        started = perf_counter()
        try:
            records = self.query(sql)
        except Exception as exc:
            logger.warning(
                "data_query backend=duckdb success=false driver_error_type=%s safe_error_code=DUCKDB_QUERY_FAILED "
                "trace_id=%s",
                type(exc).__name__,
                context.trace_id,
            )
            telemetry = QueryTelemetry(
                data_backend="duckdb",
                query_latency_ms=(perf_counter() - started) * 1000,
                row_count=0,
                success=False,
                safe_error_code="DUCKDB_QUERY_FAILED",
            )
            raise DataBackendError("DUCKDB_QUERY_FAILED", telemetry) from exc

        names = list(records[0]) if records else []
        rows = [[normalize_value(record.get(name)) for name in names] for record in records]
        return BackendQueryResult(
            columns=[BackendColumn(name=name, type="unknown") for name in names],
            rows=rows,
            row_count=len(rows),
            telemetry=QueryTelemetry(
                data_backend="duckdb",
                query_latency_ms=(perf_counter() - started) * 1000,
                row_count=len(rows),
                success=True,
            ),
        )

    def close(self) -> None:
        return None
