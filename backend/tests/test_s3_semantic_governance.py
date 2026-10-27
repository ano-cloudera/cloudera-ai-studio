from __future__ import annotations

import os
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import BACKEND_ROOT, Settings
from app.db.platform_engine import get_session_factory
from app.db.platform_models import Base
from app.main import create_app
from app.projects.bootstrap import ensure_platform_seed
from app.semantic_registry.governance_pipeline import SemanticGovernancePipeline
from app.semantic_registry.governance_types import READINESS_NOT_READY, READINESS_READY, READINESS_WITH_WARNINGS
from app.semantic_registry.semantic_diff import SemanticDiffService
from app.semantic_registry.source_validators import extract_identifier_candidates
from app.semantic_registry.sql_guard import assert_read_only_sql

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skip Postgres S3 integration tests",
)


from tests.semantic_schema_helpers import ensure_s3_governance_schema


@pytest.fixture()
def s3_client():
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
    return TestClient(create_app(settings)), factory


def test_readiness_states(s3_client):
    client, _ = s3_client
    model_id = client.post("/api/v1/semantic/models", json={"name": "Gov", "key": f"gov.{uuid.uuid4().hex[:6]}"}).json()[
        "model"
    ]["id"]
    vid = client.get(f"/api/v1/semantic/models/{model_id}/versions").json()["versions"][0]["id"]
    client.post(
        f"/api/v1/semantic/versions/{vid}/metrics",
        json={"key": "m1", "name": "m1", "expression": "SUM(x)", "source_entity_key": "missing"},
    )
    result = client.post(f"/api/v1/semantic/versions/{vid}/validate", json={"mode": "structural"}).json()
    assert result["readiness"] == READINESS_NOT_READY
    assert result["valid"] is False

    client.post(
        f"/api/v1/semantic/versions/{vid}/entities",
        json={"key": "sales", "name": "sales", "source_type": "logical", "table_name": "sales"},
    )
    metric_id = client.get(f"/api/v1/semantic/versions/{vid}/metrics").json()["metrics"][0]["id"]
    client.patch(
        f"/api/v1/semantic/versions/{vid}/metrics/{metric_id}",
        json={"source_entity_key": "sales", "business_definition": "Sales total"},
    )
    ok = client.post(f"/api/v1/semantic/versions/{vid}/validate", json={"mode": "structural"}).json()
    assert ok["valid"] is True
    assert ok["readiness"] in {READINESS_READY, READINESS_WITH_WARNINGS}


def test_validation_history_and_publish_block(s3_client):
    client, _ = s3_client
    model_id = client.post("/api/v1/semantic/models", json={"name": "Hist", "key": f"hist.{uuid.uuid4().hex[:6]}"}).json()[
        "model"
    ]["id"]
    vid = client.get(f"/api/v1/semantic/models/{model_id}/versions").json()["versions"][0]["id"]
    client.post(
        f"/api/v1/semantic/versions/{vid}/metrics",
        json={"key": "bad", "name": "bad", "expression": "SUM(x)", "source_entity_key": "nope"},
    )
    val = client.post(f"/api/v1/semantic/versions/{vid}/validate", json={"mode": "full"})
    assert val.status_code == 200
    run_id = val.json()["run_id"]
    assert run_id
    runs = client.get(f"/api/v1/semantic/versions/{vid}/validation-runs").json()["runs"]
    assert runs[0]["id"] == run_id
    detail = client.get(f"/api/v1/semantic/validation-runs/{run_id}").json()
    assert detail["issues"]
    pub = client.post(f"/api/v1/semantic/versions/{vid}/publish")
    assert pub.status_code == 422


def test_semantic_diff_breaking(s3_client):
    client, factory = s3_client
    key = f"diff.{uuid.uuid4().hex[:6]}"
    model_id = client.post("/api/v1/semantic/models", json={"name": "Diff", "key": key}).json()["model"]["id"]
    v1 = client.get(f"/api/v1/semantic/models/{model_id}/versions").json()["versions"][0]["id"]
    client.post(
        f"/api/v1/semantic/versions/{v1}/entities",
        json={"key": "sales", "name": "sales", "source_type": "logical"},
    )
    client.post(
        f"/api/v1/semantic/versions/{v1}/metrics",
        json={
            "key": "gross_sales",
            "name": "Gross Sales",
            "expression": "SUM(amount)",
            "source_entity_key": "sales",
            "business_definition": "Total",
        },
    )
    client.post(f"/api/v1/semantic/versions/{v1}/publish")
    v2 = client.post(f"/api/v1/semantic/versions/{v1}/clone").json()["version"]["id"]
    mid = client.get(f"/api/v1/semantic/versions/{v2}/metrics").json()["metrics"][0]["id"]
    client.patch(
        f"/api/v1/semantic/versions/{v2}/metrics/{mid}",
        json={"expression": "SUM(revenue)"},
    )
    diff = client.get(f"/api/v1/semantic/versions/{v2}/diff?against={v1}").json()
    assert diff["sections"]
    assert any(c.get("field") == "expression" for s in diff["sections"] if s["section"] == "metrics" for c in s["changed"])


def test_glossary_ambiguity_unit():
    with patch("app.semantic_registry.governance_pipeline.OssieRuntimeAdapter") as art:
        art.return_value.generate_artifact.return_value = MagicMock(
            content_preview="version: 1\nname: x\ndatasets: []\nmetrics: []\nrelationships: []\n",
            checksum="abc",
            metadata={"entities": 0, "metrics": 2, "dimensions": 0, "relationships": 0},
        )
        session = MagicMock()
        version = MagicMock(status="DRAFT", semantic_model_id=uuid.uuid4(), version_number=1)
        session.get.return_value = version
        session.execute.return_value.scalars.return_value.all.return_value = []
        pipeline = SemanticGovernancePipeline(session)
        issues = []

        class M:
            key = "a"
            name = "sales"
            synonyms = ["revenue"]
            expression = "SUM(x)"
            source_entity_key = "e"
            aggregation = "sum"
            business_definition = "x"
            metadata_ = {}

        class M2(M):
            key = "b"
            name = "net"

        pipeline._validate_semantic([M(), M2()], [], [], [], [MagicMock()], lambda i: issues.append(i))
        assert any(i.code == "AMBIGUOUS_TERM" for i in issues)


def test_sql_guard_blocks_mutations():
    with pytest.raises(ValueError):
        assert_read_only_sql("DROP TABLE sales")


def test_extract_identifiers():
    ids = extract_identifier_candidates("SUM(gross_amount)")
    assert "gross_amount" in ids
    assert "sum" not in ids
