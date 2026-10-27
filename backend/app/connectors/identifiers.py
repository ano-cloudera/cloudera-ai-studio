from __future__ import annotations

import re

from app.connectors.errors import ConnectorError

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_identifier(value: str, *, label: str = "identifier") -> str:
    cleaned = (value or "").strip()
    if not cleaned or not _IDENT.match(cleaned):
        raise ConnectorError("INVALID_IDENTIFIER", f"Invalid {label}: rejected characters or empty", 400)
    if len(cleaned) > 128:
        raise ConnectorError("INVALID_IDENTIFIER", f"{label} too long", 400)
    return cleaned


def quote_hive(identifier: str) -> str:
    name = validate_identifier(identifier, label="identifier")
    return f"`{name}`"


def quote_trino(identifier: str) -> str:
    name = validate_identifier(identifier, label="identifier")
    return f'"{name}"'


def qualify_hive(schema: str, table: str) -> str:
    return f"{quote_hive(schema)}.{quote_hive(table)}"


def qualify_trino(catalog: str | None, schema: str | None, table: str) -> str:
    parts = []
    if catalog:
        parts.append(quote_trino(catalog))
    if schema:
        parts.append(quote_trino(schema))
    parts.append(quote_trino(table))
    return ".".join(parts)


def quote_postgres(identifier: str) -> str:
    name = validate_identifier(identifier, label="identifier")
    return f'"{name}"'


def qualify_postgres(schema: str, table: str) -> str:
    return f"{quote_postgres(schema)}.{quote_postgres(table)}"
