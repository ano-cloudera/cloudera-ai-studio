from __future__ import annotations

import os
import uuid

import pytest
from pydantic import SecretStr

from app.core.config import BACKEND_ROOT, Settings
from app.db.platform_engine import get_session_factory
from app.db.platform_models import Base
from app.main import create_app
from app.projects.bootstrap import ensure_platform_seed

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skip semantic bulk delete integration tests",
)

from tests.semantic_schema_helpers import ensure_s3_governance_schema


@pytest.fixture()
def sem_client():
    url = os.environ["DATABASE_URL"]
    engine = __import__("app.db.platform_engine", fromlist=["get_platform_engine"]).get_platform_engine(url)
    Base.metadata.create_all(engine)
    ensure_s3_governance_schema(engine)
    factory = get_session_factory(url)
    with factory() as session:
        ensure_platform_seed(session, backend_root=BACKEND_ROOT)
    settings = Settings(
        _env_file=None,
        state_store="postgres",
        database_url=url,
        qwen_base_url="https://qwen",
        qwen_api_key=SecretStr("token"),
        qwen_model="qwen-model",
    )
    return __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(create_app(settings))


def test_metrics_bulk_delete_partial(sem_client):
    client = sem_client
    key = f"bulk.{uuid.uuid4().hex[:8]}"
    model = client.post("/api/v1/semantic/models", json={"name": "Bulk", "key": key}).json()["model"]
    vid = client.get(f"/api/v1/semantic/models/{model['id']}/versions").json()["versions"][0]["id"]
    client.post(
        f"/api/v1/semantic/versions/{vid}/entities",
        json={"key": "sales", "name": "Sales", "source_type": "logical", "table_name": "sales"},
    )
    m1 = client.post(
        f"/api/v1/semantic/versions/{vid}/metrics",
        json={"key": "m1", "name": "M1", "expression": "SUM(a)", "source_entity_key": "sales", "business_definition": "x"},
    ).json()["metric"]
    m2 = client.post(
        f"/api/v1/semantic/versions/{vid}/metrics",
        json={"key": "m2", "name": "M2", "expression": "SUM(b)", "source_entity_key": "sales", "business_definition": "x"},
    ).json()["metric"]
    resp = client.post(
        f"/api/v1/semantic/versions/{vid}/metrics/bulk-delete",
        json={"ids": [m1["id"], str(uuid.uuid4())]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["deleted_count"] == 1
    assert body["failed_count"] == 1
    assert any(f["id"] == m1["id"] for f in body["deleted"]) or any(d["id"] == m1["id"] for d in body["deleted"])
    listed = client.get(f"/api/v1/semantic/versions/{vid}/metrics").json()["metrics"]
    assert len(listed) == 1
    assert listed[0]["id"] == m2["id"]
