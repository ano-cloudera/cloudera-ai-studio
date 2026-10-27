"""Backward-compatible export — prefer app.stores.factory.build_conversation_store."""

from __future__ import annotations

from app.stores.sqlite_conversation import SQLiteConversationStore

# Legacy name used across tests and docs.
ConversationStore = SQLiteConversationStore

__all__ = ["ConversationStore", "SQLiteConversationStore"]
