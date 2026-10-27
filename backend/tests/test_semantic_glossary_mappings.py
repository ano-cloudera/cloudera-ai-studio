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
    reason="DATABASE_URL not set — skip Postgres glossary mapping tests",
)

from tests.semantic_schema_helpers import ensure_s3_governance_schema


@pytest.fixture()
def glossary_client():
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


def _draft_version(client):
    key = f"gloss.{uuid.uuid4().hex[:8]}"
    model = client.post("/api/v1/semantic/models", json={"name": "Glossary", "key": key}).json()["model"]
    vid = client.get(f"/api/v1/semantic/models/{model['id']}/versions").json()["versions"][0]["id"]
    client.post(
        f"/api/v1/semantic/versions/{vid}/entities",
        json={"key": "sales", "name": "Sales", "source_type": "logical", "table_name": "sales"},
    )
    client.post(
        f"/api/v1/semantic/versions/{vid}/metrics",
        json={
            "key": "net_sales",
            "name": "Net Sales",
            "expression": "SUM(amount)",
            "source_entity_key": "sales",
            "business_definition": "Total",
        },
    )
    client.post(
        f"/api/v1/semantic/versions/{vid}/dimensions",
        json={
            "key": "channel",
            "name": "Channel",
            "source_entity_key": "sales",
            "source_column": "channel",
            "data_type": "string",
        },
    )
    return vid


def test_create_term_with_related_objects(glossary_client):
    client = glossary_client
    vid = _draft_version(client)
    resp = client.post(
        f"/api/v1/semantic/versions/{vid}/terms",
        json={
            "key": "sell_out",
            "term": "Sell Out",
            "definition": "Retail sell-out",
            "related_entity_keys": ["sales"],
            "related_metric_keys": ["net_sales"],
            "related_dimension_keys": ["channel"],
        },
    )
    assert resp.status_code == 200, resp.text
    term = resp.json()["term"]
    assert term["related_entity_keys"] == ["sales"]
    assert term["related_metric_keys"] == ["net_sales"]
    assert term["related_dimension_keys"] == ["channel"]


def test_invalid_related_metric_rejected(glossary_client):
    client = glossary_client
    vid = _draft_version(client)
    bad = client.post(
        f"/api/v1/semantic/versions/{vid}/terms",
        json={"key": "t1", "term": "T1", "related_metric_keys": ["missing_metric"]},
    )
    assert bad.status_code == 400


def test_duplicate_mapping_deduped(glossary_client):
    client = glossary_client
    vid = _draft_version(client)
    resp = client.post(
        f"/api/v1/semantic/versions/{vid}/terms",
        json={"key": "t2", "term": "T2", "related_metric_keys": ["net_sales", "net_sales"]},
    )
    assert resp.status_code == 200
    assert resp.json()["term"]["related_metric_keys"] == ["net_sales"]
