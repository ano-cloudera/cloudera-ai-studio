"""Deleting a semantic model, on SQLite always and on Postgres when SEMANTIC_TEST_DATABASE_URL is set
(the shared conftest clears DATABASE_URL, so the older Postgres integration tests are skipped in a normal run)."""
from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import BACKEND_ROOT, Settings
from app.db.platform_engine import get_platform_engine, get_session_factory
from app.db.platform_models import Base
from app.main import create_app
from app.projects.bootstrap import ensure_platform_seed
from tests.semantic_schema_helpers import ensure_s3_governance_schema

PG_URL = os.environ.get("SEMANTIC_TEST_DATABASE_URL", "")


@pytest.fixture(params=["sqlite", "postgres"])
def s1_client(request, tmp_path):
    """The Cloudera AI deployment uses SQLite; Postgres is checked as well when SEMANTIC_TEST_DATABASE_URL is set."""
    if request.param == "postgres":
        if not PG_URL:
            pytest.skip("SEMANTIC_TEST_DATABASE_URL not set")
        url, store = PG_URL, "postgres"
    else:
        url, store = f"sqlite+pysqlite:///{tmp_path / 'semantic.db'}", "sqlite"
    engine = get_platform_engine(url)
    Base.metadata.create_all(engine)
    ensure_s3_governance_schema(engine)
    factory = get_session_factory(url)
    with factory() as session:
        ensure_platform_seed(session, backend_root=BACKEND_ROOT)
    settings = Settings(_env_file=None, state_store=store, database_url=url, qwen_base_url="https://qwen", qwen_api_key=SecretStr("token"), qwen_model="qwen-model")
    return TestClient(create_app(settings)), factory


def _model(client, label: str) -> tuple[str, str, str]:
    key = f"{label}.{uuid.uuid4().hex[:8]}"
    model = client.post("/api/v1/semantic/models", json={"name": label, "key": key}).json()["model"]
    version = client.get(f"/api/v1/semantic/models/{model['id']}/versions").json()["versions"][0]["id"]
    return model["id"], key, version


def _with_metric(client, version_id: str) -> None:
    client.post(f"/api/v1/semantic/versions/{version_id}/entities", json={"key": "sales", "name": "sales", "source_type": "logical", "table_name": "sales"})
    client.post(
        f"/api/v1/semantic/versions/{version_id}/metrics",
        json={"key": "gross_sales", "name": "Gross Sales", "expression": "SUM(amount)", "source_entity_key": "sales", "business_definition": "Total sales"},
    )


def test_an_unpublished_model_is_deleted_with_its_draft(s1_client) -> None:
    client, _ = s1_client
    model_id, key, version_id = _model(client, "draftonly")
    _with_metric(client, version_id)
    response = client.delete(f"/api/v1/semantic/models/{model_id}")
    assert response.status_code == 200, response.text
    assert response.json() == {"deleted": True, "model_id": model_id, "model_key": key, "model_name": "draftonly", "was_published": False}
    assert client.get(f"/api/v1/semantic/models/{model_id}").status_code == 404
    assert model_id not in {m["id"] for m in client.get("/api/v1/semantic/models").json()["models"]}
    assert client.delete(f"/api/v1/semantic/models/{model_id}").status_code == 404  # already gone


def test_a_published_model_needs_a_confirmation_and_then_leaves_ask_data(s1_client) -> None:
    client, _ = s1_client
    model_id, key, version_id = _model(client, "live")
    _with_metric(client, version_id)
    assert client.post(f"/api/v1/semantic/versions/{version_id}/publish").status_code == 200
    refused = client.delete(f"/api/v1/semantic/models/{model_id}")
    assert refused.status_code == 409
    assert client.get(f"/api/v1/semantic/models/{model_id}").status_code == 200  # nothing was removed
    done = client.delete(f"/api/v1/semantic/models/{model_id}", params={"confirm_published": "true"})
    assert done.status_code == 200, done.text
    assert done.json()["was_published"] is True
    assert client.get(f"/api/v1/semantic/models/{model_id}").status_code == 404
    assert client.get(f"/api/v1/semantic/resolve?semantic_model_key={key}").status_code == 404


def test_deleting_the_default_model_clears_it_from_the_ask_data_settings(s1_client) -> None:
    client, _ = s1_client
    model_id, _, _ = _model(client, "default")
    settings = client.get("/api/v1/ask-data/settings").json()["settings"]
    saved = client.put("/api/v1/ask-data/settings", json={**settings, "default_semantic_model_id": model_id})
    assert saved.status_code == 200, saved.text
    assert client.get("/api/v1/ask-data/settings").json()["settings"]["default_semantic_model_id"] == model_id
    assert client.delete(f"/api/v1/semantic/models/{model_id}").status_code == 200
    assert client.get("/api/v1/ask-data/settings").json()["settings"]["default_semantic_model_id"] is None
