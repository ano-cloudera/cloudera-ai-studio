"""Portable JSON field helpers for queries."""

from __future__ import annotations

from sqlalchemy import Integer, cast
from sqlalchemy.sql.elements import ColumnElement

from app.db.types import PlatformJSON


def json_text_field(json_column: ColumnElement, key: str) -> ColumnElement:
    """Extract a JSON scalar as text for sorting/filtering (Postgres + SQLite)."""
    return json_column[key].as_string()


def json_int_field(json_column: ColumnElement, key: str) -> ColumnElement:
    return cast(json_text_field(json_column, key), Integer)
