from __future__ import annotations

import io
import os
import uuid

import pytest
from pydantic import SecretStr
from fastapi.testclient import TestClient

from app.core.config import BACKEND_ROOT, Settings
from app.core.models import AskDataRequest
from app.db.platform_engine import get_session_factory
from app.db.platform_models import Base
from app.main import create_app
from app.projects.bootstrap import ensure_platform_seed

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set",
)


@pytest.fixture()
def knowledge_client(tmp_path):
    url = os.environ["DATABASE_URL"]
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
        document_max_file_mb=1,
        document_allowed_types="pdf,txt",
        knowledge_max_documents_per_library=100,
        qwen_base_url="https://qwen",
        qwen_api_key=SecretStr("token"),
        qwen_model="qwen-model",
    )
    app = create_app(settings)
    return TestClient(app), settings


def _create_library(client: TestClient, name: str | None = None) -> str:
    label = name or f"Lib-{uuid.uuid4().hex[:8]}"
    response = client.post("/api/v1/libraries", json={"name": label})
    assert response.status_code == 200, response.text
    return response.json()["library"]["id"]


def test_library_list_pagination_search_sort(knowledge_client):
    client, _ = knowledge_client
    lib_a = _create_library(client, f"Alpha-{uuid.uuid4().hex[:4]}")
    lib_b = _create_library(client, f"Beta-{uuid.uuid4().hex[:4]}")

    page = client.get("/api/v1/libraries?page=1&page_size=10&sort=updated_at&order=desc")
    assert page.status_code == 200
    body = page.json()
    assert "items" in body
    assert body["page"] == 1
    assert body["page_size"] == 10
    assert body["total"] >= 2
    assert any(row["id"] == lib_a for row in body["items"])
    assert any(row["id"] == lib_b for row in body["items"])
    assert "document_count" in body["items"][0]

    search = client.get("/api/v1/libraries?page=1&page_size=10&search=Alpha")
    assert search.status_code == 200
    assert all("alpha" in row["name"].lower() for row in search.json()["items"])

    invalid_sort = client.get("/api/v1/libraries?page=1&page_size=10&sort=DROP_TABLE&order=desc")
    assert invalid_sort.status_code == 200
    assert invalid_sort.json()["items"]


def test_library_rename_keeps_id(knowledge_client):
    client, _ = knowledge_client
    library_id = _create_library(client)
    renamed = client.patch(f"/api/v1/libraries/{library_id}", json={"name": f"Renamed-{uuid.uuid4().hex[:6]}"})
    assert renamed.status_code == 200
    assert renamed.json()["library"]["id"] == library_id


def test_library_delete_cascades_documents(knowledge_client):
    client, _ = knowledge_client
    library_id = _create_library(client)
    upload = client.post(
        f"/api/v1/libraries/{library_id}/documents",
        files={"file": ("note.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert upload.status_code == 200
    deleted = client.delete(f"/api/v1/libraries/{library_id}")
    assert deleted.status_code == 200
    missing = client.get(f"/api/v1/libraries/{library_id}")
    assert missing.status_code == 404


def test_document_list_pagination_and_rename(knowledge_client):
    client, _ = knowledge_client
    library_id = _create_library(client)
    upload = client.post(
        f"/api/v1/libraries/{library_id}/documents",
        files={"file": ("policy.txt", io.BytesIO(b"policy text"), "text/plain")},
    )
    doc_id = upload.json()["document"]["id"]
    listed = client.get(f"/api/v1/libraries/{library_id}/documents?page=1&page_size=10&search=policy")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    renamed = client.patch(f"/api/v1/documents/{doc_id}", json={"original_filename": "Policy Guide.txt"})
    assert renamed.status_code == 200
    assert renamed.json()["document"]["original_filename"] == "Policy Guide.txt"


def test_document_limit_enforced(knowledge_client, tmp_path):
    url = os.environ["DATABASE_URL"]
    settings = Settings(
        _env_file=None,
        state_store="postgres",
        database_url=url,
        document_storage_root=tmp_path / "limit-docs",
        document_allowed_types="txt",
        knowledge_max_documents_per_library=2,
        qwen_base_url="https://qwen",
        qwen_api_key=SecretStr("token"),
        qwen_model="qwen-model",
    )
    client = TestClient(create_app(settings))
    library_id = _create_library(client)
    for idx in range(2):
        ok = client.post(
            f"/api/v1/libraries/{library_id}/documents",
            files={"file": (f"f{idx}.txt", io.BytesIO(b"x"), "text/plain")},
        )
        assert ok.status_code == 200, ok.text
    blocked = client.post(
        f"/api/v1/libraries/{library_id}/documents",
        files={"file": ("f3.txt", io.BytesIO(b"x"), "text/plain")},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "LIBRARY_DOCUMENT_LIMIT_REACHED"


def test_chat_context_sources_model():
    req = AskDataRequest(
        session_id="s",
        question="q",
        provider="qwen",
        model="m",
        context_sources=[{"type": "knowledge_library", "id": str(uuid.uuid4()), "name": "Docs"}],
    )
    assert req.context_sources is not None
    assert req.mode == "ask_data"


def test_chat_context_sources_invalid_library(knowledge_client):
    client, _ = knowledge_client
    response = client.post(
        "/chat/stream",
        json={
            "session_id": str(uuid.uuid4()),
            "question": "hello",
            "provider": "qwen",
            "model": "qwen-model",
            "context_sources": [
                {"type": "knowledge_library", "id": str(uuid.uuid4()), "name": "Missing"},
            ],
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "library_not_found"
