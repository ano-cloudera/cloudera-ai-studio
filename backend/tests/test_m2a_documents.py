from __future__ import annotations

import io
import os
import uuid

import pytest
from pydantic import SecretStr
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.platform_engine import get_session_factory
from app.db.platform_models import Base
from app.main import create_app
from app.projects.bootstrap import ensure_platform_seed
from app.core.config import BACKEND_ROOT


pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skip Postgres M2A integration tests",
)


@pytest.fixture()
def m2a_client(tmp_path):
    url = os.environ["DATABASE_URL"]
    engine = __import__("app.db.platform_engine", fromlist=["get_platform_engine"]).get_platform_engine(url)
    Base.metadata.create_all(engine)
    factory = get_session_factory(url)
    with factory() as session:
        ensure_platform_seed(session, backend_root=BACKEND_ROOT)

    storage = tmp_path / "docs"
    settings = Settings(
        _env_file=None,
        state_store="postgres",
        database_url=url,
        document_storage_root=storage,
        document_max_file_mb=1,
        document_allowed_types="pdf,txt",
        qwen_base_url="https://qwen",
        qwen_api_key=SecretStr("token"),
        qwen_model="qwen-model",
    )
    app = create_app(settings)
    return TestClient(app), storage


def test_library_crud_and_upload(m2a_client):
    client, storage = m2a_client
    created = client.post("/api/v1/libraries", json={"name": f"UAT Library {uuid.uuid4().hex[:8]}"})
    assert created.status_code == 200, created.text
    library_id = created.json()["library"]["id"]

    listed = client.get("/api/v1/libraries")
    assert listed.status_code == 200
    assert any(row["id"] == library_id for row in listed.json()["libraries"])

    pdf = b"%PDF-1.4\n% smoke"
    upload = client.post(
        f"/api/v1/libraries/{library_id}/documents",
        files={"file": ("note.pdf", io.BytesIO(pdf), "application/pdf")},
    )
    assert upload.status_code == 200, upload.text
    body = upload.json()["document"]
    assert body["status"] in {"UPLOADED", "QUEUED"}
    assert body["original_filename"] == "note.pdf"
    assert "storage_path" not in body

    docs = client.get(f"/api/v1/libraries/{library_id}/documents")
    assert docs.status_code == 200
    assert len(docs.json()["documents"]) == 1

    doc_id = body["id"]
    deleted = client.delete(f"/api/v1/documents/{doc_id}")
    assert deleted.status_code == 200

    # binary removed
    remaining = list(storage.rglob("*"))
    assert not remaining or all(p.is_dir() for p in remaining)


def test_rejects_invalid_type(m2a_client):
    client, _ = m2a_client
    library_id = client.post("/api/v1/libraries", json={"name": f"Lib-{uuid.uuid4().hex[:6]}"}).json()["library"]["id"]
    bad = client.post(
        f"/api/v1/libraries/{library_id}/documents",
        files={"file": ("bad.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
    )
    assert bad.status_code == 400


def test_library_isolation_by_project(m2a_client):
    client, _ = m2a_client
    suffix = uuid.uuid4().hex[:6]
    lib_a = client.post("/api/v1/libraries", json={"name": f"Iso A {suffix}"}).json()["library"]["id"]
    lib_b = client.post("/api/v1/libraries", json={"name": f"Iso B {suffix}"}).json()["library"]["id"]
    assert lib_a != lib_b
    up = client.post(
        f"/api/v1/libraries/{lib_a}/documents",
        files={"file": ("a.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert up.status_code == 200
    doc_id = up.json()["document"]["id"]
    # document listed only under its library
    assert len(client.get(f"/api/v1/libraries/{lib_b}/documents").json()["documents"]) == 0
    assert len(client.get(f"/api/v1/libraries/{lib_a}/documents").json()["documents"]) == 1
    client.delete(f"/api/v1/documents/{doc_id}")
