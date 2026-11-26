"""The whole draft through the API on a real Postgres: a Postgres data source, the background draft, accepting it the way the wizard
does, then validating and publishing the version (which checks every table, column and metric against the database).

Needs a Postgres it may write to: DRAFT_TEST_DATABASE_URL=postgresql+psycopg://user:password@host:port/db (the usual DATABASE_URL is
cleared for unit tests by conftest).
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import make_url

URL = os.environ.get("DRAFT_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="DRAFT_TEST_DATABASE_URL not set")


@pytest.fixture()
def client(monkeypatch):
    from fastapi.testclient import TestClient

    from app.api.v1 import semantic
    from app.core.config import BACKEND_ROOT, Settings
    from app.db.platform_engine import get_platform_engine, get_session_factory
    from app.db.platform_models import Base
    from app.main import create_app
    from app.projects.bootstrap import ensure_platform_seed
    from tests.semantic_schema_helpers import ensure_s3_governance_schema
    from tests.test_semantic_draft import ScriptedModel

    engine = get_platform_engine(URL)
    Base.metadata.create_all(engine)
    ensure_s3_governance_schema(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS shop CASCADE"))
        conn.execute(text("CREATE SCHEMA shop"))
        conn.execute(text("CREATE TABLE shop.customers (customer_code TEXT PRIMARY KEY, segment TEXT, province TEXT)"))
        conn.execute(text(
            "CREATE TABLE shop.orders (order_id BIGINT PRIMARY KEY, customer_code TEXT, status TEXT, amount NUMERIC(12,2), "
            "duration_minutes INTEGER, order_date DATE, notes TEXT)"
        ))
        conn.execute(text(
            "INSERT INTO shop.customers SELECT 'C' || lpad(i::text, 3, '0'), CASE WHEN i % 3 = 0 THEN 'Industry' ELSE 'Retail' END, "
            "(ARRAY['Jawa Barat','Bali','Papua'])[i % 3 + 1] FROM generate_series(0, 29) i"
        ))
        conn.execute(text(
            "INSERT INTO shop.orders SELECT i, 'C' || lpad((i % 30)::text, 3, '0'), (ARRAY['Delivered','Delivered','Late','In_Transit'])[i % 4 + 1], "
            "100 + i, 30 + i % 50, DATE '2026-01-01' + (i % 200), 'note ' || i FROM generate_series(0, 399) i"
        ))
    with get_session_factory(URL)() as session:
        ensure_platform_seed(session, backend_root=BACKEND_ROOT)

    monkeypatch.setenv("DRAFT_TEST_PG_PASSWORD", make_url(URL).password or "")
    monkeypatch.setattr(semantic, "_draft_model_available", lambda request: True)
    monkeypatch.setattr(semantic, "_draft_provider_resolver", lambda request: (lambda: (ScriptedModel(), "test-model")))
    settings = Settings(
        _env_file=None,
        state_store="postgres",
        database_url=URL,
        qwen_base_url="https://qwen",
        qwen_api_key=SecretStr("token"),
        qwen_model="qwen-model",
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS shop CASCADE"))


def _postgres_source(client) -> str:
    url = make_url(URL)
    body = {
        "name": "Shop", "key": f"shop_{uuid.uuid4().hex[:6]}", "connector_type": "postgres",
        "config": {"host": url.host, "port": url.port or 5432, "database": url.database, "username": url.username, "sslmode": "disable"},
        "secret_ref": "env://DRAFT_TEST_PG_PASSWORD",
    }
    response = client.post("/api/v1/connectors", json=body)
    assert response.status_code == 200, response.text
    return response.json()["connector"]["id"]


def _wait(client, job_id: str) -> dict:
    for _ in range(200):
        job = client.get(f"/api/v1/semantic/suggestions/draft/{job_id}").json()
        if job["status"] != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("the draft did not finish")


def test_a_drafted_model_is_accepted_validated_and_published(client) -> None:
    connector = _postgres_source(client)
    started = client.post("/api/v1/semantic/suggestions/draft", json={"connection_id": connector, "tables": ["shop.orders", "shop.customers"], "language": "en"})
    assert started.status_code == 202, started.text
    job = _wait(client, started.json()["job_id"])
    assert job["status"] == "done", job
    draft = job["result"]

    metrics = {m["key"]: m for m in draft["metrics"]}
    assert set(metrics) == {"revenue", "late_rate", "average_duration", "customers"}
    assert float(metrics["revenue"]["evidence"]["value"]) == sum(100 + i for i in range(400))
    assert any(d["name"] == "Distinct Approx" and "did not run" in d["reason"] for d in draft["dropped"])  # Postgres has no APPROX_DISTINCT
    assert [r["evidence"] for r in draft["relationships"]] == [{"matched": 30, "checked": 30}]

    # What the wizard sends: a plain data model per table, and every suggestion accepted.
    model = client.post("/api/v1/semantic/models", json={"name": "Shop", "key": f"shop_{uuid.uuid4().hex[:6]}"}).json()["model"]
    selections = []
    for section, kind in (("entities", "entity"), ("metrics", "metric"), ("dimensions", "dimension"), ("relationships", "relationship"), ("glossary_suggestions", "term")):
        for item in draft[section]:
            selections.append({"suggestion_id": item["suggestion_id"], "type": kind, "accepted": True, "payload": item, "changes": {}})
    bootstrap = [
        {"connection_id": connector, "key": "orders", "name": "orders", "schema": "shop", "table_name": "orders"},
        {"connection_id": connector, "key": "customers", "name": "customers", "schema": "shop", "table_name": "customers"},
    ]
    accepted = client.post(f"/api/v1/semantic/models/{model['id']}/suggestions/accept", json={"bootstrap_tables": bootstrap, "selections": selections})
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["conflicts"] == []
    assert body["counts"] == {"entities": 2, "metrics": 4, "dimensions": 6, "relationships": 1, "terms": 1}

    version = body["version_id"]
    entities = {e["key"]: e for e in client.get(f"/api/v1/semantic/versions/{version}/entities").json()["entities"]}
    assert entities["orders"]["source_type"] == "postgres" and entities["orders"]["name"] == "Order"  # the drafted one, not the plain one
    saved = {m["key"]: m for m in client.get(f"/api/v1/semantic/versions/{version}/metrics").json()["metrics"]}
    assert saved["late_rate"]["unit"] == "percent"
    assert saved["revenue"]["metadata"]["reference_extension"] == {"headline": 1, "better": "up"}
    assert saved["late_rate"]["metadata"]["reference_extension"] == {"better": "down"}

    checked = client.post(f"/api/v1/semantic/versions/{version}/validate")
    assert checked.status_code == 200, checked.text
    report = checked.json()
    assert report["errors"] == [], report["errors"]
    published = client.post(f"/api/v1/semantic/versions/{version}/publish")
    assert published.status_code == 200, (published.text, checked.json())


def test_without_a_model_the_draft_says_what_to_do(client, monkeypatch) -> None:
    from app.api.v1 import semantic

    monkeypatch.setattr(semantic, "_draft_model_available", lambda request: False)
    response = client.post("/api/v1/semantic/suggestions/draft", json={"connection_id": str(uuid.uuid4()), "tables": ["shop.orders"]})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "no_model"
