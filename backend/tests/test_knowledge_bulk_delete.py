from __future__ import annotations

import io
import os
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
def bulk_client(tmp_path):
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
        document_allowed_types="txt",
        bulk_delete_max_items=100,
        qwen_base_url="https://qwen",
        qwen_api_key=SecretStr("token"),
        qwen_model="qwen-model",
    )
    return TestClient(create_app(settings))


def _lib(client: TestClient, name: str) -> str:
    r = client.post("/api/v1/libraries", json={"name": name})
    assert r.status_code == 200, r.text
    return r.json()["library"]["id"]


def test_library_bulk_delete_multiple(bulk_client):
    client = bulk_client
    a = _lib(client, f"A-{uuid.uuid4().hex[:6]}")
    b = _lib(client, f"B-{uuid.uuid4().hex[:6]}")
    c = _lib(client, f"C-{uuid.uuid4().hex[:6]}")
    resp = client.post("/api/v1/libraries/bulk-delete", json={"ids": [a, b, a]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["requested"] == 2
    assert body["deleted_count"] == 2
    assert client.get(f"/api/v1/libraries/{a}").status_code == 404
    assert client.get(f"/api/v1/libraries/{b}").status_code == 404
    assert client.get(f"/api/v1/libraries/{c}").status_code == 200


def test_library_bulk_delete_invalid_and_limit(bulk_client):
    client = bulk_client
    bad = client.post("/api/v1/libraries/bulk-delete", json={"ids": [str(uuid.uuid4())]})
    assert bad.status_code == 200
    assert bad.json()["failed_count"] == 1

    settings = Settings(
        _env_file=None,
        state_store="postgres",
        database_url=os.environ["DATABASE_URL"],
        document_storage_root=__import__("pathlib").Path("/tmp"),
        bulk_delete_max_items=2,
        qwen_base_url="https://qwen",
        qwen_api_key=SecretStr("token"),
        qwen_model="qwen-model",
    )
    limited = TestClient(create_app(settings))
    ids = [_lib(limited, f"L{i}-{uuid.uuid4().hex[:4]}") for i in range(3)]
    over = limited.post("/api/v1/libraries/bulk-delete", json={"ids": ids})
    assert over.status_code == 422
    assert over.json()["detail"]["code"] == "BULK_DELETE_LIMIT_EXCEEDED"


def test_document_bulk_delete(bulk_client):
    client = bulk_client
    library_id = _lib(client, f"D-{uuid.uuid4().hex[:6]}")
    doc_ids = []
    for idx in range(3):
        up = client.post(
            f"/api/v1/libraries/{library_id}/documents",
            files={"file": (f"f{idx}.txt", io.BytesIO(b"x"), "text/plain")},
        )
        assert up.status_code == 200
        doc_ids.append(up.json()["document"]["id"])
    resp = client.post(
        "/api/v1/documents/bulk-delete",
        json={"library_id": library_id, "ids": doc_ids[:2]},
    )
    assert resp.status_code == 200
    assert resp.json()["deleted_count"] == 2
    listed = client.get(f"/api/v1/libraries/{library_id}/documents")
    assert len(listed.json()["documents"]) == 1
