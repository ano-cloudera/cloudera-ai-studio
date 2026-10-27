from __future__ import annotations

import io
import os
import time
import uuid

import pytest
from pydantic import SecretStr
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import BACKEND_ROOT, Settings
from app.db.platform_engine import get_session_factory
from app.db.platform_models import Base, DocumentChunkRow, DocumentRow
from app.main import create_app
from app.projects.bootstrap import ensure_platform_seed

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set",
)


@pytest.fixture()
def m2b_client(tmp_path):
    url = os.environ["DATABASE_URL"]
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
        embedding_provider="mock",
        qdrant_url=qdrant_url,
        qdrant_collection=f"test_{uuid.uuid4().hex[:8]}",
        qwen_base_url="https://qwen",
        qwen_api_key=SecretStr("token"),
        qwen_model="qwen-model",
    )
    app = create_app(settings)
    return TestClient(app), factory, settings


def _wait_ready(client: TestClient, doc_id: str, timeout_s: float = 30.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        body = client.get(f"/api/v1/documents/{doc_id}").json()["document"]
        if body["status"] in {"READY", "FAILED"}:
            return body
        time.sleep(0.25)
    raise AssertionError("document processing timed out")


def test_upload_process_ready_reprocess_delete(m2b_client):
    client, factory, settings = m2b_client
    library_id = client.post("/api/v1/libraries", json={"name": f"M2B-{uuid.uuid4().hex[:6]}"}).json()["library"]["id"]
    text = ("Sample knowledge document line.\n" * 50).encode()
    upload = client.post(
        f"/api/v1/libraries/{library_id}/documents",
        files={"file": ("notes.txt", io.BytesIO(text), "text/plain")},
    )
    assert upload.status_code == 200, upload.text
    doc = upload.json()["document"]
    assert doc["status"] == "QUEUED"
    doc_id = doc["id"]

    final = _wait_ready(client, doc_id)
    assert final["status"] == "READY", final

    with factory() as session:
        count = session.execute(
            select(func.count()).select_from(DocumentChunkRow).where(DocumentChunkRow.document_id == uuid.UUID(doc_id))
        ).scalar_one()
        assert count > 0

    repro = client.post(f"/api/v1/documents/{doc_id}/process")
    assert repro.status_code == 200
    final2 = _wait_ready(client, doc_id)
    assert final2["status"] == "READY"
    with factory() as session:
        count2 = session.execute(
            select(func.count()).select_from(DocumentChunkRow).where(DocumentChunkRow.document_id == uuid.UUID(doc_id))
        ).scalar_one()
        assert count2 == count

    deleted = client.delete(f"/api/v1/documents/{doc_id}")
    assert deleted.status_code == 200
    with factory() as session:
        assert session.get(DocumentRow, uuid.UUID(doc_id)) is None
        assert session.execute(
            select(func.count()).select_from(DocumentChunkRow).where(DocumentChunkRow.document_id == uuid.UUID(doc_id))
        ).scalar_one() == 0

    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qmodels

    qclient = QdrantClient(url=settings.qdrant_url, timeout=10)
    remaining = qclient.count(
        collection_name=settings.qdrant_collection,
        count_filter=qmodels.Filter(
            must=[qmodels.FieldCondition(key="document_id", match=qmodels.MatchValue(value=doc_id))]
        ),
    ).count
    assert remaining == 0
