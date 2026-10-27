from __future__ import annotations

import re

from app.connectors.metadata import ColumnInfo

_NUMERIC_NORMALIZED = {"DECIMAL", "FLOAT", "DOUBLE", "NUMBER", "NUMERIC"}
_DIMENSION_NORMALIZED = {
    "STRING",
    "TEXT",
    "VARCHAR",
    "CHAR",
    "BOOLEAN",
    "BOOL",
    "DATE",
    "TIMESTAMP",
    "DATETIME",
    "TIME",
    "INTEGER",
    "INT",
    "BIGINT",
    "SMALLINT",
}
_SUFFIX_RE = re.compile(r"(_id|_code|_name|_type|_category|_region|_date|_month)$", re.IGNORECASE)


def is_dimension_candidate(column: ColumnInfo) -> bool:
    norm = (column.normalized_type or column.data_type or "").upper()
    base = norm.split("(")[0].strip()
    name = column.name.lower()

    if base in _NUMERIC_NORMALIZED:
        if _SUFFIX_RE.search(name):
            return True
        return False

    if base in _DIMENSION_NORMALIZED:
        return True

    if _SUFFIX_RE.search(name):
        return True

    return False


def suggest_dimension_candidates(columns: list[ColumnInfo]) -> list[ColumnInfo]:
    return [c for c in columns if is_dimension_candidate(c)]


def column_to_dimension_key(column_name: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", column_name.strip().lower())
    return key.strip("_")[:128] or "column"
