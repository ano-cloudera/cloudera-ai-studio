"""METADATA-001 — SQLite platform metadata portability."""

from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.db.metadata_db import is_sqlite_metadata_url, platform_metadata_configured
from app.db.platform_engine import get_platform_engine, get_session_factory
from app.db.platform_models import ConversationRow, MessageRow, UsageEventRow, WorkspaceRow
from app.projects.bootstrap import ensure_platform_seed
from app.core.models import AnalysisOutput
from app.stores.factory import build_conversation_store, build_usage_store, init_platform_metadata
from tests.conftest import isolated_settings


def _sqlite_url(tmp_path: Path) -> str:
    db = tmp_path / "metadata" / "studio.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+pysqlite:///{db.resolve()}"


@pytest.fixture
def sqlite_platform(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    url = _sqlite_url(tmp_path)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("STATE_STORE", "sqlite")
    os.environ["DATABASE_URL"] = url
    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = isolated_settings(
        state_store="sqlite",
        database_url=url,
        document_storage_root=tmp_path / "documents",
        semantic_runtime_storage_root=tmp_path / "semantic",
    )
    engine = get_platform_engine(url)
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys"))
        fk = conn.execute(text("PRAGMA foreign_keys")).scalar()
        assert fk == 1
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    import subprocess
    import sys

    backend_root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(backend_root),
        env=env,
        check=True,
        capture_output=True,
    )
    init_platform_metadata(settings)
    yield settings, url
    get_settings.cache_clear()


def test_sqlite_url_detected(sqlite_platform):
    settings, url = sqlite_platform
    assert is_sqlite_metadata_url(url)
    assert platform_metadata_configured(settings)


def test_conversation_persistence_after_reinit(sqlite_platform):
    settings, url = sqlite_platform
    store = build_conversation_store(settings)
    session_id = f"meta001-{uuid.uuid4().hex[:8]}"
    answer = AnalysisOutput(
        direct_answer="world",
        executive_summary="test",
        insights=[],
        business_implications=[],
        caveats=[],
        data_reference="n/a",
    )
    store.append(
        session_id=session_id,
        question="hello",
        answer=answer,
        rows=[],
        chart=None,
        provider="test",
        model="test-model",
    )
    factory = get_session_factory(url)
    with factory() as session:
        conv = session.execute(
            select(ConversationRow).where(ConversationRow.external_session_id == session_id)
        ).scalar_one()
        assert conv.id is not None
        msgs = session.execute(select(MessageRow).where(MessageRow.conversation_id == conv.id)).scalars().all()
        assert len(msgs) >= 1

    get_platform_engine.cache_clear()
    store2 = build_conversation_store(settings)
    history = store2.load(session_id)
    assert history


def test_usage_events_concurrent_writes(sqlite_platform):
    settings, url = sqlite_platform
    usage = build_usage_store(settings)

    def _write(i: int) -> None:
        usage.record(
            request_id=f"req-{i}",
            session_id="sess-concurrent",
            provider="test",
            model="m",
            strategy="test",
            status="ok",
            prompt_tokens=1,
            completion_tokens=1,
            llm_calls=1,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(_write, i) for i in range(24)]
        for fut in as_completed(futures):
            fut.result()

    factory = get_session_factory(url)
    with factory() as session:
        count = session.execute(select(UsageEventRow)).scalars().all()
        assert len(count) >= 24

    daily = usage.daily_totals(days=7)
    assert len(daily) >= 1
    assert daily[0]["tokens"] >= 24


def test_platform_seed_idempotent(sqlite_platform):
    settings, url = sqlite_platform
    factory = get_session_factory(url)
    with factory() as session:
        ensure_platform_seed(session, backend_root=settings.project_root.parent)
        ws = session.execute(select(WorkspaceRow).where(WorkspaceRow.slug == "default")).scalar_one()
        assert ws.slug == "default"
