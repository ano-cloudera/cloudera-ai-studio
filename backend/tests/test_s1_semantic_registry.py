from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import BACKEND_ROOT, Settings
from app.db.platform_engine import get_session_factory
from app.db.platform_models import Base, ProjectRow
from app.main import create_app
from app.projects.bootstrap import ensure_platform_seed
from app.semantic_registry.importer import OssieImporter
from app.semantic_registry.runtime_adapter import OssieRuntimeAdapter
from app.services.semantic_registry_service import SemanticModelCreate, SemanticRegistryError, SemanticRegistryService

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skip Postgres S1 integration tests",
)


from tests.semantic_schema_helpers import ensure_s3_governance_schema


@pytest.fixture()
def s1_client():
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


def test_semantic_model_version_publish_rollback(s1_client):
    client, _ = s1_client
    key = f"sem.{uuid.uuid4().hex[:8]}"
    model = client.post("/api/v1/semantic/models", json={"name": "Test", "key": key}).json()["model"]
    model_id = model["id"]
    versions = client.get(f"/api/v1/semantic/models/{model_id}/versions").json()["versions"]
    v1 = versions[0]["id"]
    client.post(
        f"/api/v1/semantic/versions/{v1}/entities",
        json={"key": "sales", "name": "sales", "source_type": "logical", "table_name": "sales"},
    )
    client.post(
        f"/api/v1/semantic/versions/{v1}/metrics",
        json={
            "key": "gross_sales",
            "name": "Gross Sales",
            "expression": "SUM(amount)",
            "source_entity_key": "sales",
            "business_definition": "Total sales",
        },
    )
    pub = client.post(f"/api/v1/semantic/versions/{v1}/publish")
    assert pub.status_code == 200, pub.text
    assert pub.json()["version"]["status"] == "ACTIVE"

    v2 = client.post(f"/api/v1/semantic/models/{model_id}/versions").json()["version"]["id"]
    client.post(
        f"/api/v1/semantic/versions/{v2}/metrics",
        json={"key": "gross_sales", "name": "Gross Sales v2", "expression": "SUM(x)", "source_entity_key": "sales"},
    )
    client.post(f"/api/v1/semantic/versions/{v2}/publish")
    client.post(f"/api/v1/semantic/versions/{v1}/rollback")
    draft = client.post(f"/api/v1/semantic/versions/{v1}/clone").json()["version"]["id"]
    discard = client.post(f"/api/v1/semantic/versions/{draft}/discard")
    assert discard.status_code == 200, discard.text
    assert discard.json()["discarded"] is True
    listed = client.get(f"/api/v1/semantic/models/{model_id}/versions").json()["versions"]
    assert all(v["id"] != draft for v in listed)
    resolved = client.get(f"/api/v1/semantic/resolve?semantic_model_key={key}")
    assert resolved.status_code == 200
    assert resolved.json()["version"]["id"] == v1


def test_patch_metric_on_draft(s1_client):
    client, _ = s1_client
    model_id = client.post("/api/v1/semantic/models", json={"name": "Patch", "key": f"patch.{uuid.uuid4().hex[:6]}"}).json()[
        "model"
    ]["id"]
    vid = client.get(f"/api/v1/semantic/models/{model_id}/versions").json()["versions"][0]["id"]
    client.post(
        f"/api/v1/semantic/versions/{vid}/entities",
        json={"key": "sales", "name": "sales", "source_type": "logical", "table_name": "sales"},
    )
    metric = client.post(
        f"/api/v1/semantic/versions/{vid}/metrics",
        json={"key": "m1", "name": "M1", "expression": "SUM(x)", "source_entity_key": "sales"},
    ).json()["metric"]
    patched = client.patch(
        f"/api/v1/semantic/versions/{vid}/metrics/{metric['id']}",
        json={"business_definition": "Updated definition", "synonyms": ["revenue"]},
    )
    assert patched.status_code == 200
    assert patched.json()["metric"]["business_definition"] == "Updated definition"
    assert patched.json()["metric"]["synonyms"] == ["revenue"]


def test_active_version_immutable(s1_client):
    client, _ = s1_client
    model_id = client.post("/api/v1/semantic/models", json={"name": "Imm", "key": f"imm.{uuid.uuid4().hex[:6]}"}).json()[
        "model"
    ]["id"]
    vid = client.get(f"/api/v1/semantic/models/{model_id}/versions").json()["versions"][0]["id"]
    client.post(
        f"/api/v1/semantic/versions/{vid}/entities",
        json={"key": "e1", "name": "e1", "source_type": "logical"},
    )
    client.post(f"/api/v1/semantic/versions/{vid}/publish")
    resp = client.post(
        f"/api/v1/semantic/versions/{vid}/entities",
        json={"key": "e2", "name": "e2", "source_type": "logical"},
    )
    assert resp.status_code == 409


def test_validation_blocks_publish(s1_client):
    client, _ = s1_client
    model_id = client.post("/api/v1/semantic/models", json={"name": "Bad", "key": f"bad.{uuid.uuid4().hex[:6]}"}).json()[
        "model"
    ]["id"]
    vid = client.get(f"/api/v1/semantic/models/{model_id}/versions").json()["versions"][0]["id"]
    client.post(
        f"/api/v1/semantic/versions/{vid}/metrics",
        json={"key": "m1", "name": "m1", "expression": "SUM(x)", "source_entity_key": "missing_entity"},
    )
    validation = client.post(f"/api/v1/semantic/versions/{vid}/validate").json()
    assert validation["valid"] is False
    pub = client.post(f"/api/v1/semantic/versions/{vid}/publish")
    assert pub.status_code == 422


def test_project_isolation(s1_client):
    client, factory = s1_client
    with factory() as session:
        _ws, project_a = ensure_platform_seed(session, backend_root=BACKEND_ROOT)
        ws_id = project_a.workspace_id
        project_b = ProjectRow(
            workspace_id=ws_id,
            slug=f"sem-iso-{uuid.uuid4().hex[:8]}",
            name="Iso B",
            ossie_root_path="projects/tempo_scan_impala",
            status="active",
        )
        session.add(project_b)
        session.commit()
        project_b_id = project_b.id

    key_a = f"iso.a.{uuid.uuid4().hex[:6]}"
    model_a = client.post("/api/v1/semantic/models", json={"name": "A", "key": key_a}).json()["model"]["id"]

    # Switch context not available in API — attempt access with wrong project via direct service
    with factory() as session:
        svc = SemanticRegistryService(session)
        with pytest.raises(SemanticRegistryError):
            svc.get_model(uuid.UUID(model_a), workspace_id=ws_id, project_id=project_b_id)


def test_ossie_import_and_artifact_preview(s1_client):
    client, factory = s1_client
    project_dir = BACKEND_ROOT / "projects" / "tempo_scan_impala"
    if not (project_dir / "ossie" / "tempo_core.ossie.yaml").is_file():
        pytest.skip("OSSIE fixture not present")
    with factory() as session:
        _ws, project = ensure_platform_seed(session, backend_root=BACKEND_ROOT)
        svc = SemanticRegistryService(session)
        key = f"import.{uuid.uuid4().hex[:8]}"
        model = svc.create_model(
            SemanticModelCreate(
                name="Import Test",
                key=key,
                workspace_id=project.workspace_id,
                project_id=project.id,
            )
        )
        summary = OssieImporter(session).import_into_model(model=model, project_dir=project_dir)
        session.commit()
    assert summary.entities > 0
    assert summary.metrics > 0
    assert summary.errors == []
    version_id = str(summary.semantic_version_id)
    preview = client.post(f"/api/v1/semantic/versions/{version_id}/artifact-preview")
    assert preview.status_code == 200
    body = preview.json()
    assert body["adapter"] == "ossie"
    assert body["checksum"]
    assert "datasets" in body["content_preview"]

    with factory() as session:
        adapter = OssieRuntimeAdapter()
        a1 = adapter.generate_artifact(session, uuid.UUID(version_id))
        a2 = adapter.generate_artifact(session, uuid.UUID(version_id))
        assert a1.checksum == a2.checksum
