from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.ai_registry.types import AdapterTestResult
from app.core.config import BACKEND_ROOT, Settings
from app.db.platform_engine import get_session_factory
from app.main import create_app
from app.projects.bootstrap import ensure_platform_seed

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skip M7A Postgres integration tests",
)

from tests.alembic_schema_helpers import clear_model_assignments, ensure_platform_schema_via_alembic


@pytest.fixture()
def m7a_client():
    url = os.environ["DATABASE_URL"]
    engine = __import__("app.db.platform_engine", fromlist=["get_platform_engine"]).get_platform_engine(url)
    ensure_platform_schema_via_alembic(engine)
    clear_model_assignments(engine)
    factory = get_session_factory(url)
    with factory() as session:
        ensure_platform_seed(session, backend_root=BACKEND_ROOT)
    settings = Settings(
        _env_file=None,
        state_store="postgres",
        database_url=url,
        qwen_base_url="https://qwen/v1",
        qwen_api_key=SecretStr("legacy-token"),
        qwen_model="qwen-legacy",
        gemini_api_key=SecretStr(""),
        openai_api_key=SecretStr(""),
    )
    return TestClient(create_app(settings)), factory


def test_m7a_provider_model_assignment_crud(m7a_client):
    client, _ = m7a_client
    os.environ["OPENAI_API_KEY"] = "sk-test-not-exposed"
    pkey = f"openai_{uuid.uuid4().hex[:6]}"
    provider = client.post(
        "/api/v1/ai/providers",
        json={
            "name": "OpenAI Test",
            "key": pkey,
            "provider_type": "OPENAI",
            "secret_ref": "env://OPENAI_API_KEY",
        },
    )
    assert provider.status_code == 200
    pid = provider.json()["provider"]["id"]
    body = provider.json()["provider"]
    assert body["secret_configured"] is True
    assert body["secret_ref"] == "env://OPENAI_API_KEY"
    assert "sk-test" not in str(provider.json())

    mkey = f"gpt_{uuid.uuid4().hex[:6]}"
    model = client.post(
        "/api/v1/ai/models",
        json={
            "provider_id": pid,
            "name": "GPT Test",
            "key": mkey,
            "model_id": "gpt-4o-mini",
            "model_type": "CHAT",
        },
    )
    assert model.status_code == 200
    mid = model.json()["model"]["id"]

    bad_assign = client.put("/api/v1/ai/assignments/EMBEDDING", json={"model_id": mid})
    assert bad_assign.status_code == 422

    assign = client.put("/api/v1/ai/assignments/ASK_DATA", json={"model_id": mid})
    assert assign.status_code == 200
    assert assign.json()["assignment"]["capability"] == "ASK_DATA"
    assert assign.json()["assignment"]["source"] == "PROJECT"

    listings = client.get("/api/v1/ai/assignments")
    assert listings.status_code == 200
    ask = next(a for a in listings.json()["assignments"] if a["capability"] == "ASK_DATA")
    assert ask["model_id"] == mid
    rag = next(a for a in listings.json()["assignments"] if a["capability"] == "RAG_GENERATION")
    assert rag["source"] == "LEGACY_FALLBACK"

    del_model = client.delete(f"/api/v1/ai/models/{mid}")
    assert del_model.status_code == 200
    assert del_model.json()["deleted"] is True

    listings_after = client.get("/api/v1/ai/assignments")
    ask_after = next(a for a in listings_after.json()["assignments"] if a["capability"] == "ASK_DATA")
    assert ask_after["source"] == "LEGACY_FALLBACK"

    del_provider = client.delete(f"/api/v1/ai/providers/{pid}")
    assert del_provider.status_code == 200
    assert del_provider.json()["deleted"] is True


def test_m7a_provider_test_mocked(m7a_client):
    client, _ = m7a_client
    os.environ["QWEN_API_KEY"] = "compat-token"
    key = f"vllm_{uuid.uuid4().hex[:6]}"
    created = client.post(
        "/api/v1/ai/providers",
        json={
            "name": "Local vLLM",
            "key": key,
            "provider_type": "OPENAI_COMPATIBLE",
            "base_url": "http://127.0.0.1:8000/v1",
            "secret_ref": "env://QWEN_API_KEY",
        },
    )
    assert created.status_code == 200
    pid = created.json()["provider"]["id"]
    ready = AdapterTestResult(status="READY", latency_ms=12.5, metadata={"endpoint": "models"})
    with patch("app.ai_registry.services.ProviderAdapterFactory.create") as factory_create:
        mock_adapter = AsyncMock()
        mock_adapter.test_connection = AsyncMock(return_value=ready)
        factory_create.return_value = mock_adapter
        resp = client.post(f"/api/v1/ai/providers/{pid}/test")
    assert resp.status_code == 200
    assert resp.json()["status"] == "READY"
    assert resp.json()["provider_type"] == "OPENAI_COMPATIBLE"


def test_legacy_models_api_still_works(m7a_client):
    client, _ = m7a_client
    resp = client.get("/models")
    assert resp.status_code == 200
    assert "models" in resp.json()
