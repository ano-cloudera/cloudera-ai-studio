from __future__ import annotations

import os
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.connectors.metadata import ColumnInfo, TableDetail
from app.core.config import BACKEND_ROOT, Settings
from app.db.platform_engine import get_session_factory
from app.db.platform_models import Base
from app.main import create_app
from app.projects.bootstrap import ensure_platform_seed

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skip Postgres C4 integration tests",
)

from tests.connector_schema_helpers import ensure_c1_connectors_schema
from tests.semantic_schema_helpers import ensure_c4_semantic_connection_schema, ensure_s3_governance_schema, ensure_s4_runtime_schema


def _mock_table_detail():
    return TableDetail(
        catalog="hive",
        schema="gold",
        name="sales_monthly",
        table_type="TABLE",
        columns=[
            ColumnInfo(name="material_code", native_type="string", normalized_type="STRING"),
            ColumnInfo(name="sell_in_bill_val", native_type="decimal", normalized_type="DECIMAL"),
        ],
        primary_key=["material_code"],
        comment=None,
    )


@pytest.fixture()
def c4_client():
    url = os.environ["DATABASE_URL"]
    engine = __import__("app.db.platform_engine", fromlist=["get_platform_engine"]).get_platform_engine(url)
    Base.metadata.create_all(engine)
    ensure_s3_governance_schema(engine)
    ensure_s4_runtime_schema(engine)
    ensure_c1_connectors_schema(engine)
    ensure_c4_semantic_connection_schema(engine)
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


@patch("app.semantic_registry.connector_resolver.MetadataDiscoveryService.describe_table")
def test_import_entity_sets_connection_id(mock_describe, c4_client):
    mock_describe.return_value = _mock_table_detail()
    client, _ = c4_client
    os.environ["DEMO_POSTGRES_PASSWORD"] = "x"
    conn = client.post(
        "/api/v1/connectors",
        json={
            "name": "PG",
            "key": f"pg.{uuid.uuid4().hex[:6]}",
            "connector_type": "postgres",
            "config": {"host": "127.0.0.1", "port": 5432, "database": "demo"},
            "secret_ref": "env://DEMO_POSTGRES_PASSWORD",
        },
    ).json()["connector"]
    cid = conn["id"]
    model = client.post("/api/v1/semantic/models", json={"name": "C4", "key": f"c4.{uuid.uuid4().hex[:6]}"}).json()["model"]
    vid = client.get(f"/api/v1/semantic/models/{model['id']}/versions").json()["versions"][0]["id"]
    imported = client.post(
        f"/api/v1/semantic/versions/{vid}/entities/import",
        json={
            "connector_id": cid,
            "schema": "gold",
            "table": "sales_monthly",
            "name": "Sales Monthly",
            "key": "sales_monthly",
            "dimension_columns": ["material_code"],
        },
    )
    assert imported.status_code == 200, imported.text
    body = imported.json()
    assert body["entity"]["connection_id"] == cid
    assert body["import"]["dimensions_created"] == 1
    dup = client.post(
        f"/api/v1/semantic/versions/{vid}/entities/import",
        json={
            "connector_id": cid,
            "schema": "gold",
            "table": "sales_monthly",
            "name": "Dup",
            "key": "dup",
        },
    )
    assert dup.status_code == 409
    blocked = client.delete(f"/api/v1/connectors/{cid}")
    assert blocked.status_code == 409


@patch("app.semantic_registry.connector_resolver.MetadataDiscoveryService.describe_table")
def test_ossie_artifact_excludes_secrets(mock_describe, c4_client):
    mock_describe.return_value = _mock_table_detail()
    client, factory = c4_client
    os.environ["DEMO_POSTGRES_PASSWORD"] = "x"
    conn = client.post(
        "/api/v1/connectors",
        json={
            "name": "PG2",
            "key": f"pg2.{uuid.uuid4().hex[:6]}",
            "connector_type": "postgres",
            "config": {"host": "127.0.0.1", "port": 5432, "database": "demo"},
            "secret_ref": "env://DEMO_POSTGRES_PASSWORD",
        },
    ).json()["connector"]
    model = client.post("/api/v1/semantic/models", json={"name": "Art", "key": f"art.{uuid.uuid4().hex[:6]}"}).json()["model"]
    vid = client.get(f"/api/v1/semantic/models/{model['id']}/versions").json()["versions"][0]["id"]
    client.post(
        f"/api/v1/semantic/versions/{vid}/entities/import",
        json={
            "connector_id": conn["id"],
            "schema": "gold",
            "table": "sales_monthly",
            "name": "Sales Monthly",
            "key": "sales_monthly",
        },
    )
    from app.semantic_registry.runtime_adapter import OssieRuntimeAdapter

    with factory() as session:
        artifact = OssieRuntimeAdapter().generate_artifact(session, uuid.UUID(vid))
    text = artifact.content
    assert "secret" not in text.lower()
    assert "env://" not in text
    assert "gold.sales_monthly" in text or "sales_monthly" in text
