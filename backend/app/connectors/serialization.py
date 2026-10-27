from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from app.db.base import normalize_value


def json_safe_value(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, dict):
        return {str(k): json_safe_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe_value(v) for v in value]
    return normalize_value(value)


def json_safe_row(row: dict[str, Any]) -> dict[str, Any]:
    return {str(k): json_safe_value(v) for k, v in row.items()}
