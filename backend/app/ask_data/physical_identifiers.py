from __future__ import annotations

from app.connectors.identifiers import quote_hive, validate_identifier


def sqlglot_dialect(connector_type: str | None, *, legacy_data_backend: str = "impala") -> str:
    if connector_type == "trino":
        return "trino"
    if connector_type == "postgres":
        return "postgres"
    if (legacy_data_backend or "impala").strip().lower() == "duckdb":
        return "duckdb"
    return "hive"


def qualified_physical_name(
    *,
    connector_type: str,
    catalog: str | None,
    schema: str | None,
    table_name: str | None,
    view_name: str | None,
) -> str:
    table = (table_name or view_name or "").strip()
    if not table:
        raise ValueError("Missing table or view name")
    tbl = validate_identifier(table, label="table")
    if connector_type == "trino":
        cat = validate_identifier(catalog or "", label="catalog") if catalog else None
        sch = validate_identifier(schema or "", label="schema") if schema else None
        parts = [p for p in (cat, sch, tbl) if p]
        if len(parts) < 2:
            raise ValueError("Trino requires catalog and schema")
        return ".".join(quote_hive(p) for p in parts)
    if connector_type == "postgres":
        sch = validate_identifier(schema or "public", label="schema")
        return f"{sch}.{tbl}"
    db = validate_identifier(schema or catalog or "default", label="schema")
    return f"{quote_hive(db)}.{quote_hive(tbl)}"


def normalize_table_key(name: str) -> str:
    cleaned = name.strip().casefold()
    return cleaned.replace("`", "").replace('"', "")
