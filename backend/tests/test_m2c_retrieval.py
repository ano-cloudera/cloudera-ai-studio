from __future__ import annotations

import io
import os
import time
import uuid

import pytest
from pydantic import SecretStr
from fastapi.testclient import TestClient

from app.core.config import BACKEND_ROOT, Settings
from app.db.platform_engine import get_session_factory
from app.db.platform_models import Base
from app.main import create_app
from app.projects.bootstrap import ensure_platform_seed

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set",
)


@pytest.fixture()
def m2c_client(tmp_path):
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
        reranker_provider="none",
        qdrant_url=qdrant_url,
        qdrant_collection=f"m2c_{uuid.uuid4().hex[:8]}",
        qwen_base_url="https://qwen",
        qwen_api_key=SecretStr("token"),
        qwen_model="qwen-model",
    )
    return TestClient(create_app(settings)), settings


def _wait_ready(client: TestClient, doc_id: str) -> None:
    deadline = time.time() + 30
    while time.time() < deadline:
        status = client.get(f"/api/v1/documents/{doc_id}").json()["document"]["status"]
        if status in {"READY", "FAILED"}:
            return
        time.sleep(0.2)
    raise AssertionError("timeout")


def test_retrieval_search_scoped(m2c_client):
    client, _ = m2c_client
    library_id = client.post("/api/v1/libraries", json={"name": f"Retrieval-{uuid.uuid4().hex[:6]}"}).json()["library"]["id"]
    content = ("Governed sell-in alpha-one metric narrative. " * 20).encode()
    upload = client.post(
        f"/api/v1/libraries/{library_id}/documents",
        files={"file": ("brief.txt", io.BytesIO(content), "text/plain")},
    )
    doc_id = upload.json()["document"]["id"]
    _wait_ready(client, doc_id)

    search = client.post(
        "/api/v1/retrieval/search",
        json={"query": "sell-in alpha-one", "library_ids": [library_id], "top_k": 5},
    )
    assert search.status_code == 200, search.text
    body = search.json()
    assert body["results"]
    assert body["citations"]
    assert body["metadata"]["embedding_ms"] >= 0
    assert all(r["library_id"] == library_id for r in body["results"])
