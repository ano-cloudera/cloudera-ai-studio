"""Knowledge ingestion startup recovery (single-backend restart hardening)."""
from __future__ import annotations

import io
import os
import threading
import time
import uuid
from unittest.mock import patch

import pytest
from pydantic import SecretStr
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import BACKEND_ROOT, Settings
from app.db.platform_engine import get_session_factory
from app.db.platform_models import Base, DocumentChunkRow, DocumentRow
from app.main import create_app
from app.projects.bootstrap import ensure_platform_seed
from app.services.knowledge_ingestion_recovery import (
    find_recoverable_documents,
    prepare_document_for_recovery,
    scan_and_enqueue_startup_recovery,
)

INTEGRATION_DATABASE_URL = os.environ.get(
    "GOLDEN_BANKING_DATABASE_URL",
    "postgresql+psycopg://m1:m1pass@127.0.0.1:55432/accelerator",
)


def _qdrant_ready() -> bool:
    url = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")
    try:
        import httpx

        return httpx.get(f"{url.rstrip('/')}/collections", timeout=3.0).status_code == 200
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("GOLDEN_BANKING_RUN_INTEGRATION", "1") != "1",
        reason="Set GOLDEN_BANKING_RUN_INTEGRATION=1",
    ),
    pytest.mark.skipif(not _qdrant_ready(), reason="Qdrant not reachable"),
]


@pytest.fixture()
def recovery_client(tmp_path):
    url = INTEGRATION_DATABASE_URL
    qdrant_url = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")
    engine = __import__("app.db.platform_engine", fromlist=["get_platform_engine"]).get_platform_engine(url)
    Base.metadata.create_all(engine)
    factory = get_session_factory(url)
    with factory() as session:
        ensure_platform_seed(session, backend_root=BACKEND_ROOT)

    settings = Settings(
        _env_file=None,
        state_store="postgres",
        database_url=url,
        document_storage_root=tmp_path / "docs",
        document_auto_process=False,
        embedding_provider="mock",
        qdrant_url=qdrant_url,
        qdrant_collection=f"rec_{uuid.uuid4().hex[:8]}",
        qwen_base_url="https://qwen",
        qwen_api_key=SecretStr("token"),
        qwen_model="qwen-model",
    )
    return TestClient(create_app(settings)), factory, settings


def _library(client: TestClient) -> str:
    return client.post("/api/v1/libraries", json={"name": f"Rec-{uuid.uuid4().hex[:6]}"}).json()["library"]["id"]


def _upload(client: TestClient, library_id: str) -> str:
    text = ("Recovery knowledge line.\n" * 40).encode()
    resp = client.post(
        f"/api/v1/libraries/{library_id}/documents",
        files={"file": ("recovery.txt", io.BytesIO(text), "text/plain")},
    )
    assert resp.status_code == 200
    return resp.json()["document"]["id"]


def test_processing_document_recovered_on_startup(recovery_client):
    client, factory, settings = recovery_client
    library_id = _library(client)
    doc_id = uuid.UUID(_upload(client, library_id))

    with factory() as session:
        row = session.get(DocumentRow, doc_id)
        assert row is not None
        row.status = "PROCESSING"
        row.metadata_json = {"processing_stage": "embed"}
        session.add(row)
        session.commit()

    def _only_target(session):
        return [row for row in find_recoverable_documents(session) if row.id == doc_id]

    with patch(
        "app.services.knowledge_ingestion_recovery.find_recoverable_documents",
        side_effect=_only_target,
    ):
        with patch("app.services.knowledge_ingestion_recovery._run_document_ingestion") as run:
            count = scan_and_enqueue_startup_recovery(settings)
            assert count == 1
            assert run.call_count == 1

    with factory() as session:
        row = session.get(DocumentRow, doc_id)
        assert row is not None
        assert row.status == "QUEUED"
        assert int((row.metadata_json or {}).get("recovery_attempts") or 0) == 1


def test_ready_documents_not_recovered(recovery_client):
    client, factory, settings = recovery_client
    library_id = _library(client)
    doc_id = uuid.UUID(_upload(client, library_id))
    with factory() as session:
        row = session.get(DocumentRow, doc_id)
        row.status = "READY"
        row.metadata_json = {"chunk_count": 2}
        session.add(row)
        session.commit()

    with factory() as session:
        ids = {r.id for r in find_recoverable_documents(session)}
        assert doc_id not in ids


def test_failed_documents_not_recovered(recovery_client):
    client, factory, settings = recovery_client
    library_id = _library(client)
    doc_id = uuid.UUID(_upload(client, library_id))
    with factory() as session:
        row = session.get(DocumentRow, doc_id)
        row.status = "FAILED"
        row.metadata_json = {"error_summary": "bad pdf"}
        session.add(row)
        session.commit()

    with factory() as session:
        ids = {r.id for r in find_recoverable_documents(session)}
        assert doc_id not in ids


def test_chat_attachment_documents_excluded(recovery_client):
    client, factory, settings = recovery_client
    library_id = _library(client)
    doc_id = uuid.UUID(_upload(client, library_id))
    with factory() as session:
        row = session.get(DocumentRow, doc_id)
        row.status = "PROCESSING"
        row.metadata_json = {"source_type": "chat_attachment"}
        session.add(row)
        session.commit()

    with factory() as session:
        ids = {r.id for r in find_recoverable_documents(session)}
        assert doc_id not in ids


def test_end_to_end_recovery_after_interrupt(recovery_client):
    client, factory, settings = recovery_client
    library_id = _library(client)
    doc_id = _upload(client, library_id)

    with factory() as session:
        row = session.get(DocumentRow, uuid.UUID(doc_id))
        row.status = "PROCESSING"
        session.add(row)
        session.commit()

    scan_and_enqueue_startup_recovery(settings)
    deadline = time.time() + 30
    while time.time() < deadline:
        body = client.get(f"/api/v1/documents/{doc_id}").json()["document"]
        if body["status"] in {"READY", "FAILED"}:
            break
        time.sleep(0.25)
    assert body["status"] == "READY"
    with factory() as session:
        count = session.execute(
            select(func.count()).select_from(DocumentChunkRow).where(DocumentChunkRow.document_id == uuid.UUID(doc_id))
        ).scalar_one()
        assert count > 0

    scan_and_enqueue_startup_recovery(settings)
    with factory() as session:
        count2 = session.execute(
            select(func.count()).select_from(DocumentChunkRow).where(DocumentChunkRow.document_id == uuid.UUID(doc_id))
        ).scalar_one()
        assert count2 == count


def test_missing_blob_marks_failed(recovery_client):
    client, factory, settings = recovery_client
    library_id = _library(client)
    doc_id = uuid.UUID(_upload(client, library_id))
    with factory() as session:
        row = session.get(DocumentRow, doc_id)
        row.status = "PROCESSING"
        row.storage_path = "missing/key.txt"
        session.add(row)
        session.commit()
        ok = prepare_document_for_recovery(settings, session, row)
        assert ok is False
        fresh = session.get(DocumentRow, doc_id)
        assert fresh.status == "FAILED"
