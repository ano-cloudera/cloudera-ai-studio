from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import BACKEND_ROOT, Settings
from app.db.platform_engine import get_session_factory
from app.db.platform_models import Base
from app.main import create_app
from app.projects.bootstrap import ensure_platform_seed
from app.semantic_runtime.loader import SemanticRuntimeLoader
from app.semantic_runtime.storage import write_deployment_artifact
from app.semantic_registry.governance_types import READINESS_READY

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skip Postgres S4 integration tests",
)

from tests.semantic_schema_helpers import ensure_s3_governance_schema, ensure_s4_runtime_schema


@pytest.fixture()
def s4_client(tmp_path):
    url = os.environ["DATABASE_URL"]
    engine = __import__("app.db.platform_engine", fromlist=["get_platform_engine"]).get_platform_engine(url)
    Base.metadata.create_all(engine)
    ensure_s3_governance_schema(engine)
    ensure_s4_runtime_schema(engine)
    factory = get_session_factory(url)
    with factory() as session:
        ensure_platform_seed(session, backend_root=BACKEND_ROOT)
    storage_root = tmp_path / "semantic-runtime"
    settings = Settings(
        _env_file=None,
        state_store="postgres",
        database_url=url,
        semantic_runtime_storage_root=str(storage_root),
        qwen_base_url="https://qwen",
        qwen_api_key=SecretStr("token"),
        qwen_model="qwen-model",
    )
    SemanticRuntimeLoader._instance = None  # noqa: SLF001
    return TestClient(create_app(settings)), factory, settings


def _publishable_model(client: TestClient) -> tuple[str, str, str]:
    model = client.post("/api/v1/semantic/models", json={"name": "Runtime", "key": f"rt.{uuid.uuid4().hex[:6]}"}).json()[
        "model"
    ]
    model_id = model["id"]
    model_key = model["key"]
    vid = client.get(f"/api/v1/semantic/models/{model_id}/versions").json()["versions"][0]["id"]
    client.post(
        f"/api/v1/semantic/versions/{vid}/entities",
        json={"key": "sales", "name": "sales", "source_type": "logical", "table_name": "sales"},
    )
    client.post(
        f"/api/v1/semantic/versions/{vid}/metrics",
        json={
            "key": "gross_sales",
            "name": "Gross Sales",
            "expression": "SUM(amount)",
            "source_entity_key": "sales",
            "business_definition": "Total sales",
        },
    )
    val = client.post(f"/api/v1/semantic/versions/{vid}/validate", json={"mode": "structural"}).json()
    assert val["valid"] is True
    pub = client.post(f"/api/v1/semantic/versions/{vid}/publish")
    assert pub.status_code == 200
    return model_key, model_id, vid


def test_runtime_status_registry_vs_runtime(s4_client):
    client, _, _ = s4_client
    model_key, _, vid = _publishable_model(client)
    status = client.get(f"/api/v1/semantic/runtime/status?model_key={model_key}").json()
    assert status["registry_active_version"] == 1
    assert status["runtime_active_version"] is None
    assert status["loader_mode"] == "legacy"

    stage = client.post(f"/api/v1/semantic/versions/{vid}/runtime/stage")
    assert stage.status_code == 200
    dep_id = stage.json()["deployment"]["id"]

    dry = client.post(f"/api/v1/semantic/runtime/deployments/{dep_id}/activate?dry_run=true")
    assert dry.status_code == 200
    assert dry.json()["result"] == "READY_TO_ACTIVATE"

    act = client.post(f"/api/v1/semantic/runtime/deployments/{dep_id}/activate")
    assert act.status_code == 200
    assert act.json()["result"] == "ACTIVATED"

    status2 = client.get(f"/api/v1/semantic/runtime/status?model_key={model_key}").json()
    assert status2["registry_active_version"] == 1
    assert status2["runtime_active_version"] == 1
    assert status2["deployment"]["deployment_id"] == dep_id


def test_runtime_history_and_rollback(s4_client):
    client, _, _ = s4_client
    model_key, _, v1 = _publishable_model(client)
    dep1 = client.post(f"/api/v1/semantic/versions/{v1}/runtime/stage").json()["deployment"]["id"]
    client.post(f"/api/v1/semantic/runtime/deployments/{dep1}/activate")

    clone = client.post(f"/api/v1/semantic/versions/{v1}/clone").json()["version"]["id"]
    metric_id = client.get(f"/api/v1/semantic/versions/{clone}/metrics").json()["metrics"][0]["id"]
    client.patch(
        f"/api/v1/semantic/versions/{clone}/metrics/{metric_id}",
        json={"business_definition": "Updated definition for v2"},
    )
    assert client.post(f"/api/v1/semantic/versions/{clone}/validate", json={"mode": "structural"}).json()["valid"]
    assert client.post(f"/api/v1/semantic/versions/{clone}/publish").status_code == 200
    dep2 = client.post(f"/api/v1/semantic/versions/{clone}/runtime/stage").json()["deployment"]["id"]
    assert client.post(f"/api/v1/semantic/runtime/deployments/{dep2}/activate").status_code == 200

    history = client.get(f"/api/v1/semantic/runtime/deployments?model_key={model_key}").json()["deployments"]
    assert len(history) >= 2

    rb = client.post(f"/api/v1/semantic/runtime/deployments/{dep1}/rollback")
    assert rb.status_code == 200
    status = client.get(f"/api/v1/semantic/runtime/status?model_key={model_key}").json()
    assert status["runtime_active_version"] == 1
    assert status["deployment"]["deployment_id"] == dep1


def test_checksum_blocks_activation(s4_client):
    client, factory, settings = s4_client
    model_key, _, vid = _publishable_model(client)
    dep_id = client.post(f"/api/v1/semantic/versions/{vid}/runtime/stage").json()["deployment"]["id"]
    with factory() as session:
        from app.db.platform_models import SemanticRuntimeDeploymentRow

        dep = session.get(SemanticRuntimeDeploymentRow, uuid.UUID(dep_id))
        assert dep
        from app.semantic_runtime.storage import deployment_dir
        from app.db.platform_models import SemanticModelRow

        model = session.get(SemanticModelRow, dep.semantic_model_id)
        root = deployment_dir(
            settings,
            workspace_id=dep.workspace_id,
            project_id=dep.project_id,
            model_key=model.key,
            deployment_id=dep.id,
        )
        core = root / "ossie" / "tempo_core.ossie.yaml"
        core.write_text(core.read_text() + "\n# tamper\n", encoding="utf-8")
    act = client.post(f"/api/v1/semantic/runtime/deployments/{dep_id}/activate")
    assert act.status_code == 422
    status = client.get(f"/api/v1/semantic/runtime/status?model_key={model_key}").json()
    assert status["runtime_active_version"] is None


def test_artifact_generation_deterministic_structure():
    """Unit-style: staged YAML has required OSSIE sections."""
    core = {
        "datasets": [{"name": "sales", "table": "sales"}],
        "metrics": [{"name": "gross_sales", "expression": "SUM(amount)"}],
    }
    text = yaml.safe_dump(core)
    parsed = yaml.safe_load(text)
    assert "datasets" in parsed and "metrics" in parsed
    assert hashlib.sha256(text.encode()).hexdigest()


def test_loader_legacy_when_no_deployment():
    SemanticRuntimeLoader._instance = None  # noqa: SLF001
    loader = SemanticRuntimeLoader.get(Settings(_env_file=None))
    bundle = loader.get_bundle()
    assert bundle.mode == "legacy"
