"""Portable SQLAlchemy column types for platform metadata (PostgreSQL + SQLite)."""

from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import Uuid

# Cross-dialect UUID (API still exposes standard string UUIDs).
PlatformUUID = Uuid(as_uuid=True)

# JSON with PostgreSQL JSONB variant for indexing/performance on Postgres.
PlatformJSON = JSON().with_variant(JSONB(), "postgresql")
