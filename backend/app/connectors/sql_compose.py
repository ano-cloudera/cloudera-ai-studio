from __future__ import annotations

from app.connectors.identifiers import (
    qualify_hive,
    qualify_postgres,
    qualify_trino,
    quote_hive,
    quote_postgres,
    quote_trino,
    validate_identifier,
)

# The sqlglot dialect that reads each connector's SQL.
SQL_DIALECT = {"impala": "hive", "trino": "trino", "postgres": "postgres"}


def qualified_table_sql(*, connector_type: str, catalog: str | None, schema: str | None, table: str) -> str:
    """The quoted, fully qualified name of a table in the connector's own SQL."""
    table = validate_identifier(table, label="table")
    if connector_type == "impala":
        sch = validate_identifier(schema or catalog or "default", label="schema")
        return qualify_hive(sch, table)
    if connector_type == "trino":
        if not schema:
            raise ValueError("schema required for Trino")
        cat = validate_identifier(catalog, label="catalog") if catalog else None
        sch = validate_identifier(schema, label="schema")
        return qualify_trino(cat, sch, table)
    if connector_type == "postgres":
        sch = validate_identifier(schema or "public", label="schema")
        return qualify_postgres(sch, table)
    raise ValueError(f"Unsupported connector type: {connector_type}")


def quote_column(connector_type: str, name: str) -> str:
    """A column name quoted for the connector's SQL; raises ConnectorError for a name that cannot be used safely."""
    if connector_type == "impala":
        return quote_hive(name)
    if connector_type == "postgres":
        return quote_postgres(name)
    return quote_trino(name)


def preview_select_sql(
    *,
    connector_type: str,
    catalog: str | None,
    schema: str | None,
    table: str,
    limit: int,
) -> str:
    limit = max(1, min(limit, 100))
    if connector_type == "trino" and not schema:
        raise ValueError("schema required for Trino preview")
    qualified = qualified_table_sql(connector_type=connector_type, catalog=catalog, schema=schema, table=table)
    return f"SELECT * FROM {qualified} LIMIT {limit}"
