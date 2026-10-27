from __future__ import annotations

import os

import pytest

from app.stores.factory import build_conversation_store, build_usage_store
from conftest import isolated_settings
from app.stores.sqlite_conversation import SQLiteConversationStore
from app.stores.sqlite_usage import SQLiteUsageStore


def test_factory_defaults_to_sqlite(tmp_path):
    settings = isolated_settings(
        state_store="sqlite",
        database_url="",
        conversation_db_path=tmp_path / "conv.sqlite",
        usage_db_path=tmp_path / "usage.sqlite",
    )
    assert isinstance(build_conversation_store(settings), SQLiteConversationStore)
    assert isinstance(build_usage_store(settings), SQLiteUsageStore)


def test_factory_sqlite_platform_database_uses_platform_stores(tmp_path):
    db = tmp_path / "studio.db"
    url = f"sqlite+pysqlite:///{db.resolve()}"
    settings = isolated_settings(
        state_store="sqlite",
        database_url=url,
        project_root=tmp_path / "projects",
    )
    from app.stores.factory import init_platform_metadata
    from app.stores.postgres_conversation import PostgresConversationStore
    from app.stores.postgres_usage import PostgresUsageStore

    init_platform_metadata(settings)
    assert isinstance(build_conversation_store(settings), PostgresConversationStore)
    assert isinstance(build_usage_store(settings), PostgresUsageStore)


def test_factory_postgres_without_url_falls_back_sqlite(tmp_path):
    settings = isolated_settings(
        state_store="postgres",
        database_url="",
        conversation_db_path=tmp_path / "conv.sqlite",
        usage_db_path=tmp_path / "usage.sqlite",
    )
    assert isinstance(build_conversation_store(settings), SQLiteConversationStore)
    assert isinstance(build_usage_store(settings), SQLiteUsageStore)


@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — skip live Postgres")
def test_factory_postgres_when_configured():
    settings = isolated_settings(
        state_store="postgres",
        database_url=os.environ["DATABASE_URL"],
    )
    conv = build_conversation_store(settings)
    usage = build_usage_store(settings)
    from app.stores.postgres_conversation import PostgresConversationStore
    from app.stores.postgres_usage import PostgresUsageStore

    assert isinstance(conv, PostgresConversationStore)
    assert isinstance(usage, PostgresUsageStore)
