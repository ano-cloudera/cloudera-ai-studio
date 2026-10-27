"""Stable encoded IDs for raw connector table context (picker + Ask Data)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass


_PREFIX = "tr"
_SEP = ":"


def _part(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return "-"
    return raw.replace(_SEP, "_")


def _unpart(value: str) -> str | None:
    if value == "-":
        return None
    return value


@dataclass(frozen=True)
class RawTableRef:
    connector_id: uuid.UUID
    catalog: str | None
    schema: str | None
    table: str


def encode_raw_table_id(
    *,
    connector_id: uuid.UUID,
    catalog: str | None,
    schema: str | None,
    table: str,
) -> str:
    name = (table or "").strip()
    if not name:
        raise ValueError("table name is required")
    return _SEP.join(
        [
            _PREFIX,
            str(connector_id),
            _part(catalog),
            _part(schema),
            _part(name),
        ]
    )


def decode_raw_table_id(raw_id: str) -> RawTableRef | None:
    text = (raw_id or "").strip()
    if not text.startswith(f"{_PREFIX}{_SEP}"):
        return None
    parts = text.split(_SEP)
    if len(parts) != 5:
        return None
    try:
        connector_id = uuid.UUID(parts[1])
    except ValueError:
        return None
    table = _unpart(parts[4])
    if not table:
        return None
    return RawTableRef(
        connector_id=connector_id,
        catalog=_unpart(parts[2]),
        schema=_unpart(parts[3]),
        table=table,
    )


def is_encoded_raw_table_id(raw_id: str) -> bool:
    return decode_raw_table_id(raw_id) is not None
