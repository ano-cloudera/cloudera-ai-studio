from __future__ import annotations

import re

NormalizedType = str

_STRING = re.compile(r"(char|text|string|uuid|json|enum|varchar|nvarchar)", re.I)
_INTEGER = re.compile(r"(^int$|^integer$|smallint|tinyint|int2|int4)", re.I)
_BIGINT = re.compile(r"(bigint|int8|long)", re.I)
_DECIMAL = re.compile(r"(decimal|numeric|number|money)", re.I)
_FLOAT = re.compile(r"(float|double|real)", re.I)
_BOOLEAN = re.compile(r"(bool|boolean)", re.I)
_DATE = re.compile(r"(^date$)", re.I)
_TIMESTAMP = re.compile(r"(timestamp|datetime)", re.I)
_BINARY = re.compile(r"(binary|blob|bytea|varbinary)", re.I)
_ARRAY = re.compile(r"(array|\[\])", re.I)
_MAP = re.compile(r"(map<|map\()", re.I)
_STRUCT = re.compile(r"(struct<|row\()", re.I)


def normalize_data_type(native_type: str) -> NormalizedType:
    raw = (native_type or "").strip()
    if not raw:
        return "UNKNOWN"
    base = raw.split("(")[0].strip()
    if _STRUCT.search(raw):
        return "STRUCT"
    if _MAP.search(raw):
        return "MAP"
    if _ARRAY.search(raw):
        return "ARRAY"
    if _BOOLEAN.search(base):
        return "BOOLEAN"
    if _BIGINT.search(base):
        return "BIGINT"
    if _INTEGER.search(base):
        return "INTEGER"
    if _DECIMAL.search(base):
        return "DECIMAL"
    if _FLOAT.search(base):
        return "FLOAT"
    if _TIMESTAMP.search(base):
        return "TIMESTAMP"
    if _DATE.search(base):
        return "DATE"
    if _BINARY.search(base):
        return "BINARY"
    if _STRING.search(base):
        return "STRING"
    return "UNKNOWN"


def normalize_table_type(raw: str | None) -> str:
    value = (raw or "TABLE").upper().replace(" ", "_")
    if "MATERIALIZED" in value:
        return "MATERIALIZED_VIEW"
    if "VIEW" in value:
        return "VIEW"
    if value in {"TABLE", "BASE TABLE", "BASE_TABLE", "EXTERNAL_TABLE"}:
        return "TABLE"
    return "OTHER"
