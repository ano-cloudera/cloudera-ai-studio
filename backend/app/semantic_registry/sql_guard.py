from __future__ import annotations

import re

_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|CALL|EXECUTE)\b",
    re.IGNORECASE,
)


def assert_read_only_sql(sql: str) -> None:
    stripped = sql.strip()
    if not stripped:
        raise ValueError("Empty SQL")
    if _FORBIDDEN.search(stripped):
        raise ValueError("Forbidden SQL keyword in validation query")
    if ";" in stripped.rstrip(";"):
        raise ValueError("Multiple SQL statements are not allowed")
