from __future__ import annotations

import sqlglot
from sqlglot import exp

from app.connectors.errors import ConnectorError


def assert_connector_readonly_sql(sql: str) -> None:
    stripped = (sql or "").strip()
    if not stripped:
        raise ConnectorError("QUERY_REJECTED", "Empty SQL", 400)
    if ";" in stripped.rstrip(";"):
        raise ConnectorError("QUERY_REJECTED", "Multiple SQL statements are not allowed", 400)
    try:
        statements = sqlglot.parse(stripped, read="hive")
    except Exception as exc:
        raise ConnectorError("QUERY_REJECTED", f"SQL parse error: {exc}", 400) from exc
    if len(statements) != 1:
        raise ConnectorError("QUERY_REJECTED", "Only one SQL statement is allowed", 400)
    root = statements[0]
    allowed = (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.Describe, exp.Command)
    if isinstance(root, exp.Command):
        # EXPLAIN SELECT ...
        if not str(root).upper().startswith("EXPLAIN"):
            raise ConnectorError("QUERY_REJECTED", "Only EXPLAIN commands are allowed", 400)
        return
    if not isinstance(root, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise ConnectorError(
            "QUERY_REJECTED",
            f"Only read-only SELECT/WITH queries are allowed, got {type(root).__name__}",
            400,
        )
    forbidden_types = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Drop,
        exp.Create,
        exp.Alter,
        exp.TruncateTable,
        exp.Grant,
        exp.Revoke,
    )
    for node in root.walk():
        if isinstance(node, forbidden_types):
            raise ConnectorError("QUERY_REJECTED", "Mutating SQL is not allowed", 400)
