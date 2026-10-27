from __future__ import annotations

from app.connectors.identifiers import qualify_hive, qualify_postgres, qualify_trino, validate_identifier


def preview_select_sql(
    *,
    connector_type: str,
    catalog: str | None,
    schema: str | None,
    table: str,
    limit: int,
) -> str:
    table = validate_identifier(table, label="table")
    limit = max(1, min(limit, 100))
    if connector_type == "impala":
        sch = validate_identifier(schema or catalog or "default", label="schema")
        return f"SELECT * FROM {qualify_hive(sch, table)} LIMIT {limit}"
    if connector_type == "trino":
        if not schema:
            raise ValueError("schema required for Trino preview")
        cat = validate_identifier(catalog, label="catalog") if catalog else None
        sch = validate_identifier(schema, label="schema")
        return f"SELECT * FROM {qualify_trino(cat, sch, table)} LIMIT {limit}"
    if connector_type == "postgres":
        sch = validate_identifier(schema or "public", label="schema")
        return f"SELECT * FROM {qualify_postgres(sch, table)} LIMIT {limit}"
    raise ValueError(f"Unsupported connector type: {connector_type}")
