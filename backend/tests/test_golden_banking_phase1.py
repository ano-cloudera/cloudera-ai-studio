"""Golden Path Banking Demo — Phase 1 (raw Ask Data, no semantic layer)."""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "demo"))

from banking_data_generator import generate_customers, generate_transactions  # noqa: E402

from app.ask_data.structured_context_resolver import resolve_structured_ask
from app.ask_data.table_context_id import encode_raw_table_id
from app.ask_data.validation import validate_ask_data_sql
from app.core.config import BACKEND_ROOT, Settings
from app.core.models import AnalysisOutput, AskDataRequest, ChatContextSource, QueryPlan
from app.db.platform_engine import get_session_factory
from app.db.platform_models import Base, ConnectorRow
from app.main import create_app
from app.projects.bootstrap import ensure_platform_seed
from app.semantic.context import SemanticContextService
from conftest import isolated_settings
from tests.connector_schema_helpers import ensure_c1_connectors_schema
from tests.semantic_schema_helpers import ensure_s3_governance_schema, ensure_s4_runtime_schema

BANKING_URL = os.environ.get("BANKING_DEMO_URL", "postgresql://m1:m1pass@127.0.0.1:55432/banking_demo")
INTEGRATION_DATABASE_URL = os.environ.get(
    "GOLDEN_BANKING_DATABASE_URL",
    "postgresql+psycopg://m1:m1pass@127.0.0.1:55432/accelerator",
)


def _banking_seeded() -> bool:
    try:
        import psycopg

        with psycopg.connect(BANKING_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM banking_demo.customers")
                return int(cur.fetchone()[0]) >= 200
    except Exception:
        return False


skip_no_banking = pytest.mark.skipif(not _banking_seeded(), reason="banking_demo not seeded")


requires_platform_db = pytest.mark.skipif(
    not os.environ.get("GOLDEN_BANKING_RUN_INTEGRATION", "1") == "1",
    reason="Set GOLDEN_BANKING_RUN_INTEGRATION=1 to run platform DB integration tests",
)


@pytest.fixture()
def phase1_client(monkeypatch: pytest.MonkeyPatch):
    from app.db.metadata_db import is_sqlite_metadata_url

    url = INTEGRATION_DATABASE_URL
    state = "sqlite" if is_sqlite_metadata_url(url) else "postgres"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("STATE_STORE", state)
    engine = __import__("app.db.platform_engine", fromlist=["get_platform_engine"]).get_platform_engine(url)
    Base.metadata.create_all(engine)
    ensure_s3_governance_schema(engine)
    ensure_s4_runtime_schema(engine)
    ensure_c1_connectors_schema(engine)
    factory = get_session_factory(url)
    with factory() as session:
        ensure_platform_seed(session, backend_root=BACKEND_ROOT)
    os.environ["BANKING_DEMO_PG_PASSWORD"] = os.environ.get("BANKING_DEMO_PG_PASSWORD", "m1pass")
    settings = isolated_settings(
        state_store=state,
        database_url=url,
    )
    return TestClient(create_app(settings)), factory


def test_banking_seed_deterministic():
    a = generate_customers(seed=42)
    b = generate_customers(seed=42)
    assert a == b
    tx_a = generate_transactions(a, seed=42)
    tx_b = generate_transactions(b, seed=42)
    assert tx_a == tx_b
    assert len(a) == 250
    assert len(tx_a) == 1000


@requires_platform_db
@skip_no_banking
def test_banking_connector_and_metadata(phase1_client):
    client, _ = phase1_client
    key = f"golden_banking_pg.{uuid.uuid4().hex[:6]}"
    created = client.post(
        "/api/v1/connectors",
        json={
            "name": "Banking PostgreSQL",
            "key": key,
            "connector_type": "postgres",
            "config": {
                "host": "127.0.0.1",
                "port": 55432,
                "database": "banking_demo",
                "username": "m1",
                "sslmode": "prefer",
            },
            "secret_ref": "env://BANKING_DEMO_PG_PASSWORD",
        },
    )
    assert created.status_code == 200
    cid = created.json()["connector"]["id"]
    test = client.post(f"/api/v1/connectors/{cid}/test")
    assert test.status_code == 200
    assert test.json()["status"] == "SUCCESS"
    tables = client.get(f"/api/v1/connectors/{cid}/tables", params={"schema": "banking_demo"})
    assert tables.status_code == 200
    names = {t["name"] for t in tables.json()["tables"]}
    assert {"customers", "transactions"}.issubset(names)
    client.delete(f"/api/v1/connectors/{cid}")


def _fake_banking_provider(*, sql: str):
    class FakeProvider:
        async def generate_structured(self, _messages, response_model, **_kwargs):
            if response_model is QueryPlan:
                return QueryPlan(
                    strategy="sql_fallback",
                    sql=sql,
                    metrics=[],
                    dimensions=[],
                    filters={},
                )
            return AnalysisOutput(
                direct_answer="ok",
                executive_summary="Synthetic banking raw-table answer.",
                insights=[],
                business_implications=[],
                caveats=[],
                data_reference="banking_demo.customers",
                chart_spec=None,
            )

    def _provider(_state, _deps):
        return FakeProvider()

    return _provider


@requires_platform_db
@skip_no_banking
def test_raw_chat_customers_active_count(phase1_client, monkeypatch: pytest.MonkeyPatch):
    client, _ = phase1_client
    monkeypatch.setenv("BANKING_DEMO_PG_PASSWORD", "m1pass")
    key = f"golden.chat.{uuid.uuid4().hex[:6]}"
    created = client.post(
        "/api/v1/connectors",
        json={
            "name": "Banking PostgreSQL",
            "key": key,
            "connector_type": "postgres",
            "config": {
                "host": "127.0.0.1",
                "port": 55432,
                "database": "banking_demo",
                "username": "m1",
                "sslmode": "prefer",
            },
            "secret_ref": "env://BANKING_DEMO_PG_PASSWORD",
        },
    )
    cid = created.json()["connector"]["id"]
    table_id = encode_raw_table_id(
        connector_id=uuid.UUID(cid),
        catalog=None,
        schema="banking_demo",
        table="customers",
    )
    sql = (
        "SELECT COUNT(d.customer_id) AS active_customers FROM banking_demo.customers d "
        "WHERE d.customer_status = 'Active'"
    )
    chat_service = client.app.state.chat_service
    with patch(
        "app.graph.workflow._provider",
        _fake_banking_provider(sql=sql),
    ), patch.object(
        chat_service, "_prepare_registry_request", side_effect=lambda request, capability=None: request
    ):
        resp = client.post(
            "/chat",
            json={
                "session_id": f"golden-{uuid.uuid4().hex[:8]}",
                "question": "How many active customers are there?",
                "provider": "qwen",
                "model": "/models/Qwen3.8-27B-AWQ",
                "context_sources": [{"type": "table", "id": table_id, "name": "customers"}],
            },
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "SUCCESS", body
    assert body.get("context_mode") == "RAW_TABLE"
    assert body["data"]["row_count"] >= 1
    assert body["strategy"] == "sql_fallback"
    client.delete(f"/api/v1/connectors/{cid}")


@requires_platform_db
@skip_no_banking
def test_raw_chat_multi_table_segment_total(phase1_client, monkeypatch: pytest.MonkeyPatch):
    client, _ = phase1_client
    monkeypatch.setenv("BANKING_DEMO_PG_PASSWORD", "m1pass")
    key = f"golden.join.{uuid.uuid4().hex[:6]}"
    created = client.post(
        "/api/v1/connectors",
        json={
            "name": "Banking PostgreSQL",
            "key": key,
            "connector_type": "postgres",
            "config": {
                "host": "127.0.0.1",
                "port": 55432,
                "database": "banking_demo",
                "username": "m1",
                "sslmode": "prefer",
            },
            "secret_ref": "env://BANKING_DEMO_PG_PASSWORD",
        },
    )
    cid = created.json()["connector"]["id"]
    table_id = encode_raw_table_id(
        connector_id=uuid.UUID(cid),
        catalog=None,
        schema="banking_demo",
        table="transactions",
    )
    sql = (
        "SELECT c.segment, SUM(t.amount) AS total_amount "
        "FROM banking_demo.transactions t "
        "JOIN banking_demo.customers c ON c.customer_id = t.customer_id "
        "WHERE t.status = 'Success' "
        "GROUP BY c.segment"
    )
    chat_service = client.app.state.chat_service
    with patch(
        "app.graph.workflow._provider",
        _fake_banking_provider(sql=sql),
    ), patch.object(
        chat_service, "_prepare_registry_request", side_effect=lambda request, capability=None: request
    ):
        resp = client.post(
            "/chat",
            json={
                "session_id": f"golden-{uuid.uuid4().hex[:8]}",
                "question": "Which customers segment has the highest total transaction amount?",
                "provider": "qwen",
                "model": "/models/Qwen3.8-27B-AWQ",
                "context_sources": [{"type": "table", "id": table_id, "name": "transactions"}],
            },
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "SUCCESS", body
    assert body.get("context_mode") == "RAW_TABLE"
    assert body["data"]["row_count"] >= 1
    client.delete(f"/api/v1/connectors/{cid}")


@skip_no_banking
def test_raw_join_sql_governance():
    ctx = SemanticContextService.__new__(SemanticContextService)
    state = {
        "datasource_context": {
            "legacy_fallback": False,
            "connector_type": "postgres",
            "dialect": "postgres",
            "allowed_physical_tables": ["banking_demo.customers", "banking_demo.transactions"],
        },
        "raw_table_policy": {
            "qualified_name": "banking_demo.transactions",
            "columns": ["amount", "customer_id", "status"],
            "tables": [
                {
                    "qualified_name": "banking_demo.transactions",
                    "columns": ["amount", "customer_id", "status", "channel", "transaction_id"],
                },
                {
                    "qualified_name": "banking_demo.customers",
                    "columns": ["customer_id", "segment", "customer_status"],
                },
            ],
        },
    }
    sql = (
        "SELECT c.segment, SUM(t.amount) AS total_amount "
        "FROM banking_demo.transactions t "
        "JOIN banking_demo.customers c ON c.customer_id = t.customer_id "
        "WHERE t.status = 'Success' "
        "GROUP BY c.segment"
    )
    ok = validate_ask_data_sql(sql, ctx, state=state, max_rows=200)
    assert ok.valid, ok.error


@requires_platform_db
@skip_no_banking
def test_raw_table_resolution_and_sql_execution(phase1_client, monkeypatch: pytest.MonkeyPatch):
    """Resolver + connector SQL path for @customers (no semantic layer)."""
    client, factory = phase1_client
    monkeypatch.setenv("BANKING_DEMO_PG_PASSWORD", "m1pass")
    key = f"golden.{uuid.uuid4().hex[:6]}"
    created = client.post(
        "/api/v1/connectors",
        json={
            "name": "Banking PostgreSQL",
            "key": key,
            "connector_type": "postgres",
            "config": {
                "host": "127.0.0.1",
                "port": 55432,
                "database": "banking_demo",
                "username": "m1",
                "sslmode": "prefer",
            },
            "secret_ref": "env://BANKING_DEMO_PG_PASSWORD",
        },
    )
    assert created.status_code == 200
    cid = uuid.UUID(created.json()["connector"]["id"])
    table_id = encode_raw_table_id(
        connector_id=cid,
        catalog=None,
        schema="banking_demo",
        table="customers",
    )
    from app.db.metadata_db import is_sqlite_metadata_url

    _state = "sqlite" if is_sqlite_metadata_url(INTEGRATION_DATABASE_URL) else "postgres"
    settings = isolated_settings(state_store=_state, database_url=INTEGRATION_DATABASE_URL)
    req = AskDataRequest(
        session_id="golden",
        question="How many active customers are there?",
        provider="qwen",
        model="/models/Qwen3.8-27B-AWQ",
        context_sources=[ChatContextSource(type="table", id=table_id, name="customers")],
    )
    with factory() as session:
        from app.projects.resolver import load_default_project

        project = load_default_project(settings)
        assert project is not None
        out = resolve_structured_ask(
            session,
            settings=settings,
            workspace_id=project.workspace_id,
            project_id=project.id,
            request=req,
            semantic_context=SemanticContextService.__new__(SemanticContextService),
            question=req.question,
        )
        assert out.explicit_error is None, out.explicit_error
        assert out.resolution is not None
        assert out.context_mode == "RAW_TABLE"
        sql = (
            "SELECT COUNT(d.customer_id) AS active_customers FROM banking_demo.customers d "
            "WHERE d.customer_status = 'Active'"
        )
        state = {
            "datasource_context": out.resolution.get("datasource_context"),
            "raw_table_policy": out.resolution.get("raw_table_policy"),
        }
        ctx = SemanticContextService.__new__(SemanticContextService)
        validated = validate_ask_data_sql(sql, ctx, state=state, max_rows=200)
        assert validated.valid, validated.error
        from app.connectors.factory import ConnectorFactory
        from app.connectors.secrets import EnvironmentSecretProvider

        row = session.get(ConnectorRow, cid)
        adapter = ConnectorFactory(settings, EnvironmentSecretProvider()).create(
            row.connector_type, dict(row.config or {}), secret_ref=row.secret_ref
        )
        result = adapter.execute_readonly_query(validated.sql, max_rows=10)
        assert result.rows and int(result.rows[0].get("active_customers", 0)) > 0
    client.delete(f"/api/v1/connectors/{cid}")
