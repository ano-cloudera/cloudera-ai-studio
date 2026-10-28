from __future__ import annotations

import os
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.connectors.base import ConnectionTestResult
from app.connectors.errors import ConnectorError
from app.connectors.postgres_connector import PostgresConnector
from app.connectors.sql_safety import assert_connector_readonly_sql
from app.core.config import BACKEND_ROOT, Settings
from app.db.platform_engine import get_session_factory
from app.db.platform_models import Base, ConnectorRow, ProjectRow, WorkspaceRow
from app.main import create_app
from app.projects.bootstrap import ensure_platform_seed

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skip Postgres C1 integration tests",
)

from tests.connector_schema_helpers import ensure_c1_connectors_schema
from tests.semantic_schema_helpers import ensure_s3_governance_schema, ensure_s4_runtime_schema


@pytest.fixture()
def c1_client():
    url = os.environ["DATABASE_URL"]
    engine = __import__("app.db.platform_engine", fromlist=["get_platform_engine"]).get_platform_engine(url)
    Base.metadata.create_all(engine)
    ensure_s3_governance_schema(engine)
    ensure_s4_runtime_schema(engine)
    ensure_c1_connectors_schema(engine)
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
    return TestClient(create_app(settings)), factory, settings


def test_sql_safety_accepts_select_rejects_dml():
    assert_connector_readonly_sql("SELECT 1")
    assert_connector_readonly_sql("WITH x AS (SELECT 1) SELECT * FROM x")
    with pytest.raises(ConnectorError) as exc:
        assert_connector_readonly_sql("INSERT INTO t VALUES (1)")
    assert exc.value.code == "QUERY_REJECTED"
    with pytest.raises(ConnectorError):
        assert_connector_readonly_sql("DROP TABLE t")


def test_connector_crud_and_secret_safety(c1_client):
    client, _, _ = c1_client
    os.environ["DEMO_POSTGRES_PASSWORD"] = "secret-value-not-in-api"
    key = f"local_pg.{uuid.uuid4().hex[:6]}"
    body = {
        "name": "Local Demo PostgreSQL",
        "key": key,
        "connector_type": "postgres",
        "config": {"host": "127.0.0.1", "port": 5432, "database": "demo_data", "username": "demo"},
        "secret_ref": "env://DEMO_POSTGRES_PASSWORD",
    }
    created = client.post("/api/v1/connectors", json=body)
    assert created.status_code == 200
    payload = created.json()["connector"]
    assert payload["credentials_configured"] is True
    assert payload["secret_ref"] == "env://DEMO_POSTGRES_PASSWORD"
    assert "secret-value" not in str(created.json())
    cid = payload["id"]

    listed = client.get("/api/v1/connectors").json()["connectors"]
    assert any(c["id"] == cid for c in listed)

    dup = client.post("/api/v1/connectors", json=body)
    assert dup.status_code == 409

    patched = client.patch(f"/api/v1/connectors/{cid}", json={"description": "updated"})
    assert patched.status_code == 200
    assert patched.json()["connector"]["description"] == "updated"

    caps = client.get(f"/api/v1/connectors/{cid}/capabilities")
    assert caps.status_code == 200
    assert caps.json()["capabilities"]["schemas"] is True

    deleted = client.delete(f"/api/v1/connectors/{cid}")
    assert deleted.status_code == 200


def test_project_isolation(c1_client):
    client, factory, _ = c1_client
    from sqlalchemy import select

    with factory() as session:
        ws = session.execute(select(WorkspaceRow)).scalars().first()
        other = ProjectRow(
            workspace_id=ws.id,
            slug=f"other-{uuid.uuid4().hex[:6]}",
            name="Other",
            ossie_root_path="projects/reference_impala",
            status="active",
        )
        session.add(other)
        session.commit()
        other_id = other.id

    key = f"iso.{uuid.uuid4().hex[:6]}"
    row = client.post(
        "/api/v1/connectors",
        json={
            "name": "Iso",
            "key": key,
            "connector_type": "trino",
            "config": {"host": "localhost", "port": 8080, "catalog": "memory"},
        },
    ).json()["connector"]
    cid = row["id"]

    with factory() as session:
        connector = session.get(ConnectorRow, uuid.UUID(cid))
        connector.project_id = other_id
        session.commit()

    assert client.get(f"/api/v1/connectors/{cid}").status_code == 404


def test_postgres_connector_not_using_database_url(c1_client):
    _, _, settings = c1_client
    cfg = {"host": "127.0.0.1", "port": 5432, "database": "demo_data", "username": "demo"}
    conn = PostgresConnector(__import__("app.connectors.config", fromlist=["PostgresConnectorConfig"]).PostgresConnectorConfig.model_validate(cfg), password="x")
    assert settings.database_url
    assert "demo_data" in conn._dsn
    assert conn._dsn != settings.database_url


def test_connection_test_mock(c1_client):
    client, _, _ = c1_client
    created = client.post(
        "/api/v1/connectors",
        json={
            "name": "Impala Dev",
            "key": f"imp.{uuid.uuid4().hex[:6]}",
            "connector_type": "impala",
            "config": {"host": "localhost", "port": 21050, "database": "gold", "auth_type": "plain", "username": "u"},
            "secret_ref": "env://MISSING_SECRET",
        },
    )
    assert created.status_code == 200
    cid = created.json()["connector"]["id"]
    mock_adapter = MagicMock()
    mock_adapter.test_connection.return_value = ConnectionTestResult(
        status="SUCCESS",
        latency_ms=12.5,
        message="ok",
        server_version="impala",
        capabilities={"supports_sql": True},
    )
    mock_adapter.get_capabilities.return_value = __import__(
        "app.connectors.capabilities", fromlist=["IMPALA_CAPABILITIES"]
    ).IMPALA_CAPABILITIES
    with patch("app.connectors.service.ConnectorFactory.create", return_value=mock_adapter):
        result = client.post(f"/api/v1/connectors/{cid}/test")
    assert result.status_code == 200
    assert result.json()["status"] == "SUCCESS"
