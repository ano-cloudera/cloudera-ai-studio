from __future__ import annotations

import os
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.connectors.base import ConnectionTestResult
from app.connectors.discovery import MetadataDiscoveryService
from app.connectors.errors import ConnectorError
from app.connectors.identifiers import validate_identifier
from app.connectors.metadata import ColumnInfo, SamplePreview, SchemaInfo, TableDetail, TableInfo
from app.connectors.type_normalization import normalize_data_type
from app.core.config import BACKEND_ROOT, Settings
from app.db.platform_engine import get_session_factory
from app.db.platform_models import Base
from app.main import create_app
from app.projects.bootstrap import ensure_platform_seed

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skip Postgres C2 integration tests",
)

from tests.connector_schema_helpers import ensure_c1_connectors_schema
from tests.semantic_schema_helpers import ensure_s3_governance_schema, ensure_s4_runtime_schema


@pytest.fixture()
def c2_client():
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
        connector_metadata_cache_ttl_seconds=60,
        qwen_base_url="https://qwen",
        qwen_api_key=SecretStr("token"),
        qwen_model="qwen-model",
    )
    return TestClient(create_app(settings)), factory


def test_identifier_rejects_injection():
    with pytest.raises(ConnectorError):
        validate_identifier("foo; DROP TABLE x", label="schema")
    with pytest.raises(ConnectorError):
        validate_identifier('a" OR 1=1', label="table")


def test_type_normalization():
    assert normalize_data_type("VARCHAR(255)") == "STRING"
    assert normalize_data_type("BIGINT") == "BIGINT"
    assert normalize_data_type("NUMERIC(10,2)") == "DECIMAL"
    assert normalize_data_type("TIMESTAMP WITH TIME ZONE") == "TIMESTAMP"


def test_metadata_describe_and_preview_api(c2_client):
    client, _ = c2_client
    cid = client.post(
        "/api/v1/connectors",
        json={
            "name": "Trino",
            "key": f"trino.{uuid.uuid4().hex[:6]}",
            "connector_type": "trino",
            "config": {"host": "localhost", "port": 8080, "catalog": "memory", "schema": "default"},
        },
    ).json()["connector"]["id"]

    mock_adapter = MagicMock()
    mock_adapter.get_capabilities.return_value.to_api_dict.return_value = {"metadata": True, "sample_preview": True}
    mock_adapter.list_schemas.return_value = [SchemaInfo(name="default", catalog="memory")]
    mock_adapter.list_tables.return_value = [TableInfo(name="sales", schema="default", catalog="memory", table_type="TABLE")]
    mock_adapter.describe_table_detail.return_value = TableDetail(
        catalog="memory",
        schema="default",
        name="sales",
        table_type="TABLE",
        columns=[ColumnInfo(name="id", data_type="bigint", native_type="bigint", normalized_type="BIGINT")],
    )
    mock_adapter.default_context.return_value = ("memory", "default")
    mock_adapter.execute_readonly_query.return_value = MagicMock(
        columns=["id"],
        rows=[{"id": 1}],
        row_count=1,
    )

    with patch("app.connectors.discovery.ConnectorRegistryService.build_adapter", return_value=mock_adapter):
        tables = client.get("/api/v1/connectors/{}/tables?schema=default&search=sales".format(cid))
        assert tables.status_code == 200
        assert tables.json()["tables"][0]["name"] == "sales"

        desc = client.post(
            f"/api/v1/connectors/{cid}/metadata/describe",
            json={"catalog": "memory", "schema": "default", "table": "sales"},
        )
        assert desc.status_code == 200
        assert desc.json()["table"]["columns"][0]["normalized_type"] == "BIGINT"

        preview = client.post(
            f"/api/v1/connectors/{cid}/metadata/preview",
            json={"catalog": "memory", "schema": "default", "table": "sales", "limit": 5},
        )
        assert preview.status_code == 200
        assert preview.json()["preview"]["row_count"] == 1


def test_enhanced_connection_test(c2_client):
    client, _ = c2_client
    cid = client.post(
        "/api/v1/connectors",
        json={
            "name": "PG",
            "key": f"pg.{uuid.uuid4().hex[:6]}",
            "connector_type": "postgres",
            "config": {"host": "127.0.0.1", "port": 5432, "database": "demo_data", "username": "demo"},
            "secret_ref": "env://DEMO_POSTGRES_PASSWORD",
        },
    ).json()["connector"]["id"]
    mock_adapter = MagicMock()
    mock_adapter.test_connection.return_value = ConnectionTestResult(
        status="SUCCESS",
        latency_ms=10.0,
        message="ok",
        server_version="PostgreSQL 16",
        server_name="127.0.0.1",
        default_schema="public",
        phases={"network": "PASS", "authentication": "PASS", "session": "PASS", "metadata": "PASS"},
        capabilities={"sql": True, "metadata": True},
    )
    mock_adapter.get_capabilities.return_value.to_api_dict.return_value = {"sql": True}
    with patch("app.connectors.service.ConnectorFactory.create", return_value=mock_adapter):
        res = client.post(f"/api/v1/connectors/{cid}/test")
    assert res.status_code == 200
    body = res.json()
    assert body["phases"]["session"] == "PASS"
    assert body["default_schema"] == "public"


def test_pagination_on_tables(c2_client):
    client, _ = c2_client
    cid = client.post(
        "/api/v1/connectors",
        json={
            "name": "PG2",
            "key": f"pg2.{uuid.uuid4().hex[:6]}",
            "connector_type": "postgres",
            "config": {"host": "127.0.0.1", "port": 5432, "database": "demo_data"},
        },
    ).json()["connector"]["id"]
    tables = [TableInfo(name=f"t{i}", schema="public", table_type="TABLE") for i in range(150)]
    mock_adapter = MagicMock()
    mock_adapter.list_tables.return_value = tables
    mock_adapter.default_context.return_value = (None, "public")
    with patch("app.connectors.discovery.ConnectorRegistryService.build_adapter", return_value=mock_adapter):
        page = client.get(f"/api/v1/connectors/{cid}/tables?schema=public&limit=50&offset=100")
    assert page.status_code == 200
    assert len(page.json()["tables"]) == 50
    assert page.json()["total"] == 150
