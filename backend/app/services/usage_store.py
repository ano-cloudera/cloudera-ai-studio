"""Backward-compatible export — prefer app.stores.factory.build_usage_store."""

from __future__ import annotations

from app.stores.sqlite_usage import SQLiteUsageStore

UsageStore = SQLiteUsageStore

__all__ = ["UsageStore", "SQLiteUsageStore"]
