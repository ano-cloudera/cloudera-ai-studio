from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from time import perf_counter

from app.core.config import Settings, get_settings
from app.db.impala_backend import ImpalaBackend, is_impala_configured
from app.semantic_registry.sql_guard import assert_read_only_sql

logger = logging.getLogger(__name__)


@dataclass
class ColumnInfo:
    name: str
    data_type: str = ""


@dataclass
class SourceCheckResult:
    ok: bool
    skipped: bool = False
    message: str = ""
    columns: dict[str, ColumnInfo] = field(default_factory=dict)


class SemanticSourceValidator(ABC):
    engine: str

    @abstractmethod
    def health(self) -> tuple[str, str]:
        """Return (status, label) e.g. connected / unavailable."""

    @abstractmethod
    def table_exists(self, *, catalog: str | None, schema: str | None, table: str) -> SourceCheckResult:
        ...

    @abstractmethod
    def load_columns(self, *, catalog: str | None, schema: str | None, table: str) -> SourceCheckResult:
        ...

    def validate_limit_zero(self, sql: str) -> SourceCheckResult:
        try:
            assert_read_only_sql(sql)
            if "limit" not in sql.lower():
                sql = f"{sql.rstrip()} LIMIT 0"
            self._run_query(sql)
            return SourceCheckResult(ok=True)
        except Exception as exc:
            return SourceCheckResult(ok=False, message=str(exc))

    @abstractmethod
    def _run_query(self, sql: str) -> list[dict]:
        ...


def is_trino_configured(settings: Settings) -> bool:
    return bool(settings.trino_host.strip() and settings.trino_catalog.strip())


class ImpalaSemanticSourceValidator(SemanticSourceValidator):
    engine = "impala"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._backend = ImpalaBackend(self.settings)
        self._column_cache: dict[str, dict[str, ColumnInfo]] = {}
        self._use_duckdb = self.settings.data_backend.strip().lower() == "duckdb"

    def health(self) -> tuple[str, str]:
        if self._use_duckdb:
            from app.db.duckdb_governed_backend import is_duckdb_governed_configured

            return ("connected" if is_duckdb_governed_configured(self.settings) else "unavailable", "Impala (duckdb dev)")
        if not is_impala_configured(self.settings):
            return ("unavailable", "Impala")
        return ("connected", "Impala")

    def _run_query(self, sql: str) -> list[dict]:
        assert_read_only_sql(sql)
        timeout = self.settings.semantic_validation_timeout_seconds
        started = perf_counter()
        if self._use_duckdb:
            from app.db.duckdb_governed_backend import DuckDBGovernedBackend

            rows = DuckDBGovernedBackend(self.settings).query(sql)
        else:
            rows = self._backend.query(sql)
        if perf_counter() - started > timeout:
            raise TimeoutError("Semantic source validation timed out")
        return rows

    def _qualify(self, catalog: str | None, schema: str | None, table: str) -> str:
        parts = [p for p in (catalog, schema or self.settings.impala_database, table) if p]
        return ".".join(parts) if len(parts) > 1 else table

    def table_exists(self, *, catalog: str | None, schema: str | None, table: str) -> SourceCheckResult:
        status, _ = self.health()
        if status != "connected":
            return SourceCheckResult(ok=True, skipped=True, message="Impala unavailable; source checks skipped")
        qual = self._qualify(catalog, schema, table)
        try:
            self._run_query(f"SELECT * FROM {qual} LIMIT 0")
            return SourceCheckResult(ok=True)
        except Exception as exc:
            return SourceCheckResult(ok=False, message=str(exc))

    def load_columns(self, *, catalog: str | None, schema: str | None, table: str) -> SourceCheckResult:
        cache_key = self._qualify(catalog, schema, table)
        if cache_key in self._column_cache:
            return SourceCheckResult(ok=True, columns=self._column_cache[cache_key])
        status, _ = self.health()
        if status != "connected":
            return SourceCheckResult(ok=True, skipped=True, message="Impala unavailable; column checks skipped")
        qual = self._qualify(catalog, schema, table)
        try:
            if self._use_duckdb:
                rows = self._run_query(f"DESCRIBE {qual}")
                cols = {
                    str(r.get("column_name") or r.get("Field") or list(r.values())[0]).lower(): ColumnInfo(
                        name=str(r.get("column_name") or r.get("Field") or list(r.values())[0]),
                        data_type=str(r.get("column_type") or r.get("Type") or ""),
                    )
                    for r in rows
                }
            else:
                rows = self._run_query(f"DESCRIBE {qual}")
                cols = {
                    str(r.get("name", "")).lower(): ColumnInfo(name=str(r.get("name", "")), data_type=str(r.get("type", "")))
                    for r in rows
                    if r.get("name")
                }
            self._column_cache[cache_key] = cols
            return SourceCheckResult(ok=True, columns=cols)
        except Exception as exc:
            return SourceCheckResult(ok=False, message=str(exc))


class TrinoSemanticSourceValidator(SemanticSourceValidator):
    engine = "trino"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def health(self) -> tuple[str, str]:
        if not is_trino_configured(self.settings):
            return ("not_configured", "Trino")
        return ("connected", "Trino")

    def _run_query(self, sql: str) -> list[dict]:
        assert_read_only_sql(sql)
        try:
            import trino
        except ImportError as exc:
            raise RuntimeError("trino package not installed") from exc
        conn = trino.dbapi.connect(
            host=self.settings.trino_host,
            port=self.settings.trino_port,
            user=self.settings.trino_user or "trino",
            catalog=self.settings.trino_catalog,
            auth=None if not self.settings.trino_password else trino.auth.BasicAuthentication(
                self.settings.trino_user, self.settings.trino_password
            ),
        )
        cur = conn.cursor()
        try:
            cur.execute(sql)
            cols = [d[0] for d in cur.description or []]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            cur.close()
            conn.close()

    def table_exists(self, *, catalog: str | None, schema: str | None, table: str) -> SourceCheckResult:
        status, _ = self.health()
        if status == "not_configured":
            return SourceCheckResult(ok=True, skipped=True, message="Trino not configured")
        cat = catalog or self.settings.trino_catalog
        qual = ".".join(p for p in (cat, schema, table) if p)
        try:
            self._run_query(f"SELECT * FROM {qual} LIMIT 0")
            return SourceCheckResult(ok=True)
        except Exception as exc:
            return SourceCheckResult(ok=False, message=str(exc))

    def load_columns(self, *, catalog: str | None, schema: str | None, table: str) -> SourceCheckResult:
        status, _ = self.health()
        if status == "not_configured":
            return SourceCheckResult(ok=True, skipped=True, message="Trino not configured")
        cat = catalog or self.settings.trino_catalog
        qual = ".".join(p for p in (cat, schema, table) if p)
        try:
            rows = self._run_query(f"DESCRIBE {qual}")
            cols = {
                str(r.get("Column", list(r.values())[0])).lower(): ColumnInfo(
                    name=str(r.get("Column", list(r.values())[0])),
                    data_type=str(r.get("Type", "")),
                )
                for r in rows
            }
            return SourceCheckResult(ok=True, columns=cols)
        except Exception as exc:
            return SourceCheckResult(ok=False, message=str(exc))


def get_source_validator(source_type: str, settings: Settings | None = None) -> SemanticSourceValidator | None:
    settings = settings or get_settings()
    if source_type == "impala":
        return ImpalaSemanticSourceValidator(settings)
    if source_type == "trino":
        return TrinoSemanticSourceValidator(settings)
    return None


_IDENT = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")


def extract_identifier_candidates(expression: str) -> set[str]:
    stop = {"sum", "avg", "count", "min", "max", "distinct", "as", "from", "where", "and", "or", "case", "when", "then", "else", "end"}
    return {m.group(1).lower() for m in _IDENT.finditer(expression) if m.group(1).lower() not in stop}
