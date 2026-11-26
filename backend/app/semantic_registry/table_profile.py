"""What a table holds, read with a few read-only queries, so a semantic model can be drafted from the data and not from column names.

Everything is computed on a sample (the first `sample_size` rows) except the row count, so a large table costs about the same as a
small one. The same plain SQL (COUNT, COUNT DISTINCT, MIN, MAX, GROUP BY) runs on Trino, Impala and Postgres; only the quoting of names
differs. A query that fails leaves that part of the profile empty: a profile with gaps is still useful, a failed draft is not.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from app.connectors.errors import ConnectorError
from app.connectors.identifiers import validate_identifier
from app.connectors.metadata import ColumnInfo
from app.connectors.serialization import json_safe_value
from app.connectors.sql_compose import quote_column

logger = logging.getLogger(__name__)

# run(sql, max_rows) -> rows as dicts. In the service it is the connector's read-only query; in tests, any database.
Runner = Callable[[str, int], list[dict[str, Any]]]

SAMPLE_SIZE = 50_000
TOP_VALUES = 10
_UNPROFILED = {"STRUCT", "MAP", "ARRAY", "BINARY"}
_ORDERED = {"INTEGER", "BIGINT", "DECIMAL", "FLOAT", "DATE", "TIMESTAMP"}
_NUMERIC = {"INTEGER", "BIGINT", "DECIMAL", "FLOAT"}
_LISTED = {"STRING", "BOOLEAN", "UNKNOWN"}  # always show the most common values
_LISTED_IF_FEW = {"INTEGER", "BIGINT"}  # a code stored as a number (status 1/2/3, year)
_FEW = 50
_STATS_CHUNK = 25


@dataclass
class ColumnProfile:
    name: str
    native_type: str
    normalized_type: str
    comment: str | None = None
    non_null: int | None = None
    distinct: int | None = None
    minimum: Any = None
    maximum: Any = None
    top_values: list[tuple[Any, int]] = field(default_factory=list)

    @property
    def numeric(self) -> bool:
        return self.normalized_type in _NUMERIC

    def for_prompt(self, sample_rows: int) -> dict[str, Any]:
        out: dict[str, Any] = {"name": self.name, "type": self.native_type or self.normalized_type}
        if self.comment:
            out["comment"] = self.comment
        if self.non_null is not None and sample_rows:
            out["filled_pct"] = round(100.0 * self.non_null / sample_rows, 1)
        if self.distinct is not None:
            out["distinct"] = self.distinct
        if self.minimum is not None or self.maximum is not None:
            out["range"] = [self.minimum, self.maximum]
        if self.top_values:
            out["common_values"] = [[_short(v), n] for v, n in self.top_values]
        return out


@dataclass
class TableProfile:
    connector_type: str
    catalog: str | None
    schema: str | None
    table: str
    table_sql: str
    row_count: int | None = None
    sample_rows: int = 0
    columns: list[ColumnProfile] = field(default_factory=list)
    skipped_columns: list[str] = field(default_factory=list)
    primary_key: list[str] | None = None
    comment: str | None = None
    notes: list[str] = field(default_factory=list)

    def column(self, name: str) -> ColumnProfile | None:
        wanted = name.strip().lower()
        return next((c for c in self.columns if c.name.lower() == wanted), None)

    def for_prompt(self) -> dict[str, Any]:
        out: dict[str, Any] = {"table": self.table, "row_count": self.row_count, "profiled_rows": self.sample_rows}
        if self.comment:
            out["comment"] = self.comment
        if self.primary_key:
            out["declared_primary_key"] = self.primary_key
        out["columns"] = [c.for_prompt(self.sample_rows) for c in self.columns]
        return out


def _short(value: Any, limit: int = 60) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[: limit - 1] + "…"
    return value


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _value(row: dict[str, Any], key: str) -> Any:
    """A column of a result row, whatever case the database gave the alias."""
    if key in row:
        return row[key]
    lowered = {str(k).lower(): v for k, v in row.items()}
    return lowered.get(key.lower())


def sample_sql(table_sql: str, sample_size: int = SAMPLE_SIZE) -> str:
    return f"(SELECT * FROM {table_sql} LIMIT {int(sample_size)}) s"


def usable_columns(columns: list[ColumnInfo]) -> tuple[list[ColumnInfo], list[str]]:
    """The columns a profile (and a draft) can use: a plain name and a scalar type."""
    usable: list[ColumnInfo] = []
    skipped: list[str] = []
    for column in columns:
        try:
            validate_identifier(column.name, label="column")
        except ConnectorError:
            skipped.append(column.name)
            continue
        if (column.normalized_type or "UNKNOWN") in _UNPROFILED:
            skipped.append(column.name)
            continue
        usable.append(column)
    return usable, skipped


def profile_table(
    run: Runner,
    *,
    connector_type: str,
    catalog: str | None,
    schema: str | None,
    table: str,
    table_sql: str,
    columns: list[ColumnInfo],
    primary_key: list[str] | None = None,
    comment: str | None = None,
    sample_size: int = SAMPLE_SIZE,
    max_columns: int = 80,
    workers: int = 6,
) -> TableProfile:
    usable, skipped = usable_columns(columns)
    if len(usable) > max_columns:
        skipped.extend(c.name for c in usable[max_columns:])
        usable = usable[:max_columns]
    profile = TableProfile(
        connector_type=connector_type,
        catalog=catalog,
        schema=schema,
        table=table,
        table_sql=table_sql,
        columns=[
            ColumnProfile(
                name=c.name,
                native_type=c.native_type or c.data_type,
                normalized_type=c.normalized_type or "UNKNOWN",
                comment=c.comment,
            )
            for c in usable
        ],
        skipped_columns=skipped,
        primary_key=primary_key,
        comment=comment,
    )
    source = sample_sql(table_sql, sample_size)

    try:
        rows = run(f"SELECT COUNT(*) AS row_count FROM {table_sql}", 1)
        profile.row_count = _int(_value(rows[0], "row_count")) if rows else None
    except Exception as exc:  # noqa: BLE001 - a view can be slow to count; the sample still tells most
        logger.info("profile_row_count_failed table=%s error=%s", table, type(exc).__name__)
        profile.notes.append("The table's row count could not be read.")

    for start in range(0, len(profile.columns), _STATS_CHUNK):
        chunk = list(enumerate(profile.columns))[start : start + _STATS_CHUNK]
        parts = ["COUNT(*) AS sample_rows"]
        for index, col in chunk:
            q = quote_column(connector_type, col.name)
            parts.append(f"COUNT({q}) AS nn_{index}")
            parts.append(f"COUNT(DISTINCT {q}) AS nd_{index}")
            if col.normalized_type in _ORDERED:
                parts.append(f"MIN({q}) AS mn_{index}")
                parts.append(f"MAX({q}) AS mx_{index}")
        try:
            rows = run(f"SELECT {', '.join(parts)} FROM {source}", 1)
        except Exception as exc:  # noqa: BLE001
            logger.info("profile_stats_failed table=%s error=%s", table, type(exc).__name__)
            profile.notes.append("Some column statistics could not be read.")
            continue
        if not rows:
            continue
        row = rows[0]
        profile.sample_rows = _int(_value(row, "sample_rows")) or profile.sample_rows
        for index, col in chunk:
            col.non_null = _int(_value(row, f"nn_{index}"))
            col.distinct = _int(_value(row, f"nd_{index}"))
            if col.normalized_type in _ORDERED:
                col.minimum = json_safe_value(_value(row, f"mn_{index}"))
                col.maximum = json_safe_value(_value(row, f"mx_{index}"))

    def listed(col: ColumnProfile) -> bool:
        if col.non_null == 0:
            return False
        if col.normalized_type in _LISTED:
            return True
        return col.normalized_type in _LISTED_IF_FEW and col.distinct is not None and col.distinct <= _FEW

    def top_values(col: ColumnProfile) -> list[tuple[Any, int]]:
        q = quote_column(connector_type, col.name)
        sql = f"SELECT {q} AS v, COUNT(*) AS n FROM {source} WHERE {q} IS NOT NULL GROUP BY {q} ORDER BY n DESC LIMIT {TOP_VALUES}"
        try:
            rows = run(sql, TOP_VALUES)
        except Exception as exc:  # noqa: BLE001
            logger.info("profile_top_values_failed table=%s column=%s error=%s", table, col.name, type(exc).__name__)
            return []
        return [(json_safe_value(_value(r, "v")), _int(_value(r, "n")) or 0) for r in rows]

    wanted = [c for c in profile.columns if listed(c)]
    if wanted:
        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(wanted)))) as pool:
            for col, values in zip(wanted, pool.map(top_values, wanted)):
                col.top_values = values
    return profile


@dataclass
class ExpressionCheck:
    ok: bool
    value: Any = None
    error: str | None = None


def check_expressions(run: Runner, *, table_sql: str, expressions: dict[str, str], sample_size: int | None = SAMPLE_SIZE) -> dict[str, ExpressionCheck]:
    """Run each metric expression once, on the sample or (sample_size None) on the whole table: one query for all of them, and one
    each only when that query fails, to find which one is wrong. A metric that cannot run on the data is never offered."""
    if not expressions:
        return {}
    source = sample_sql(table_sql, sample_size) if sample_size else table_sql
    keys = list(expressions)
    try:
        select = ", ".join(f"{expressions[k]} AS m_{i}" for i, k in enumerate(keys))
        rows = run(f"SELECT {select} FROM {source}", 1)
        row = rows[0] if rows else {}
        return {k: ExpressionCheck(ok=True, value=json_safe_value(_value(row, f"m_{i}"))) for i, k in enumerate(keys)}
    except Exception:  # noqa: BLE001 - find the culprit below
        pass
    out: dict[str, ExpressionCheck] = {}
    for key in keys:
        try:
            rows = run(f"SELECT {expressions[key]} AS m_0 FROM {source}", 1)
            out[key] = ExpressionCheck(ok=True, value=json_safe_value(_value(rows[0], "m_0")) if rows else None)
        except Exception as exc:  # noqa: BLE001
            message = getattr(exc, "message", None) or str(exc)
            out[key] = ExpressionCheck(ok=False, error=message.splitlines()[0][:200] if message else type(exc).__name__)
    return out


@dataclass
class JoinCheck:
    checked: int
    matched: int

    @property
    def ratio(self) -> float:
        return self.matched / self.checked if self.checked else 0.0


def check_join(
    run: Runner,
    *,
    connector_type: str,
    from_table_sql: str,
    from_column: str,
    to_table_sql: str,
    to_column: str,
    probe: int = 200,
) -> JoinCheck | None:
    """How many of up to `probe` distinct values of the many side are found on the one side. None when the check cannot run (types
    that do not compare, a missing column): a join the data cannot confirm is not offered."""
    fc = quote_column(connector_type, from_column)
    tc = quote_column(connector_type, to_column)
    probe_sql = f"(SELECT DISTINCT {fc} AS v FROM {from_table_sql} WHERE {fc} IS NOT NULL LIMIT {int(probe)}) s"
    try:
        total = run(f"SELECT COUNT(*) AS n FROM {probe_sql}", 1)
        matched = run(f"SELECT COUNT(*) AS n FROM {probe_sql} WHERE s.v IN (SELECT {tc} FROM {to_table_sql})", 1)
    except Exception as exc:  # noqa: BLE001
        logger.info("join_check_failed from=%s.%s error=%s", from_table_sql, from_column, type(exc).__name__)
        return None
    return JoinCheck(checked=_int(_value(total[0], "n")) or 0 if total else 0, matched=_int(_value(matched[0], "n")) or 0 if matched else 0)
