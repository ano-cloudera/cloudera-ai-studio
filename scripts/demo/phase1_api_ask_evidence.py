#!/usr/bin/env python3
"""Emit Phase 1 Raw Ask API evidence (TestClient + mocked LLM, real banking DB)."""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "tests"))
sys.path.insert(0, str(ROOT / "scripts" / "demo"))

from banking_data_generator import generate_customers  # noqa: E402
from conftest import isolated_settings  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.ask_data.table_context_id import encode_raw_table_id  # noqa: E402
from app.core.config import BACKEND_ROOT  # noqa: E402
from app.core.models import AnalysisOutput, AskDataRequest, ChatContextSource, QueryPlan  # noqa: E402
from app.db.platform_engine import get_session_factory  # noqa: E402
from app.db.platform_models import Base  # noqa: E402
from app.main import create_app  # noqa: E402
from app.projects.bootstrap import ensure_platform_seed  # noqa: E402
from tests.connector_schema_helpers import ensure_c1_connectors_schema  # noqa: E402
from tests.semantic_schema_helpers import ensure_s3_governance_schema, ensure_s4_runtime_schema  # noqa: E402

OUT = ROOT / "testing" / "evidence" / "golden-path" / "PHASE1" / "api-ask-responses.json"
INTEGRATION_DATABASE_URL = os.environ.get(
    "GOLDEN_BANKING_DATABASE_URL",
    "postgresql+psycopg://m1:m1pass@127.0.0.1:55432/accelerator",
)


def _fake_provider(sql: str):
    class FakeProvider:
        async def generate_structured(self, _messages, response_model, **_kwargs):
            if response_model is QueryPlan:
                return QueryPlan(strategy="sql_fallback", sql=sql, metrics=[], dimensions=[], filters={})
            return AnalysisOutput(
                direct_answer="evidence",
                executive_summary="Phase 1 raw table evidence.",
                insights=[],
                business_implications=[],
                caveats=[],
                data_reference="banking_demo",
                chart_spec=None,
            )

    def _provider(_state, _deps):
        return FakeProvider()

    return _provider


def main() -> int:
    try:
        import psycopg

        with psycopg.connect(
            os.environ.get("BANKING_DEMO_URL", "postgresql://m1:m1pass@127.0.0.1:55432/banking_demo")
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM banking_demo.customers")
                if int(cur.fetchone()[0]) < 200:
                    print("banking_demo not seeded", file=sys.stderr)
                    return 1
    except Exception as exc:
        print("banking db unavailable", exc, file=sys.stderr)
        return 1

    os.environ["BANKING_DEMO_PG_PASSWORD"] = os.environ.get("BANKING_DEMO_PG_PASSWORD", "m1pass")
    engine = __import__("app.db.platform_engine", fromlist=["get_platform_engine"]).get_platform_engine(
        INTEGRATION_DATABASE_URL
    )
    Base.metadata.create_all(engine)
    ensure_s3_governance_schema(engine)
    ensure_s4_runtime_schema(engine)
    ensure_c1_connectors_schema(engine)
    factory = get_session_factory(INTEGRATION_DATABASE_URL)
    with factory() as session:
        ensure_platform_seed(session, backend_root=BACKEND_ROOT)

    from app.db.metadata_db import is_sqlite_metadata_url

    state = "sqlite" if is_sqlite_metadata_url(INTEGRATION_DATABASE_URL) else "postgres"
    settings = isolated_settings(state_store=state, database_url=INTEGRATION_DATABASE_URL)
    client = TestClient(create_app(settings))
    key = f"golden.evidence.{uuid.uuid4().hex[:6]}"
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
    customers_id = encode_raw_table_id(
        connector_id=uuid.UUID(cid), catalog=None, schema="banking_demo", table="customers"
    )
    tx_id = encode_raw_table_id(
        connector_id=uuid.UUID(cid), catalog=None, schema="banking_demo", table="transactions"
    )
    scenarios = [
        (
            "raw_customers_active_count",
            customers_id,
            "customers",
            "How many active customers are there?",
            "SELECT COUNT(d.customer_id) AS active_customers FROM banking_demo.customers d "
            "WHERE d.customer_status = 'Active'",
        ),
        (
            "raw_transactions_total_amount",
            tx_id,
            "transactions",
            "What is the total transaction amount?",
            "SELECT SUM(d.amount) AS total_amount FROM banking_demo.transactions d WHERE d.status = 'Success'",
        ),
        (
            "raw_transactions_failed_count",
            tx_id,
            "transactions",
            "How many failed transactions are there?",
            "SELECT COUNT(d.transaction_id) AS failed_count FROM banking_demo.transactions d "
            "WHERE d.status = 'Failed'",
        ),
        (
            "raw_transactions_amount_by_channel",
            tx_id,
            "transactions",
            "Break down transaction amount by channel.",
            "SELECT d.channel, SUM(d.amount) AS total_amount FROM banking_demo.transactions d "
            "WHERE d.status = 'Success' GROUP BY d.channel",
        ),
        (
            "raw_multi_table_segment_total",
            tx_id,
            "transactions",
            "Which customers segment has the highest total transaction amount?",
            "SELECT c.segment, SUM(t.amount) AS total_amount FROM banking_demo.transactions t "
            "JOIN banking_demo.customers c ON c.customer_id = t.customer_id "
            "WHERE t.status = 'Success' GROUP BY c.segment",
        ),
    ]
    chat_service = client.app.state.chat_service
    results = []
    for name, table_id, label, question, sql in scenarios:
        with patch("app.graph.workflow._provider", _fake_provider(sql)), patch.object(
            chat_service, "_prepare_registry_request", side_effect=lambda request, capability=None: request
        ):
            resp = client.post(
                "/chat",
                json={
                    "session_id": f"evidence-{name}",
                    "question": question,
                    "provider": "qwen",
                    "model": "/models/Qwen3.8-27B-AWQ",
                    "context_sources": [{"type": "table", "id": table_id, "name": label}],
                },
            )
        body = resp.json()
        results.append(
            {
                "scenario": name,
                "status_code": resp.status_code,
                "status": body.get("status"),
                "context_mode": body.get("context_mode"),
                "strategy": body.get("strategy"),
                "row_count": (body.get("data") or {}).get("row_count"),
                "raw_data_badge": body.get("context_mode") == "RAW_TABLE",
            }
        )
    client.delete(f"/api/v1/connectors/{cid}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "deterministic_seed_rows": len(generate_customers(seed=42)),
        "scenarios": results,
        "all_success": all(r["status"] == "SUCCESS" and r["context_mode"] == "RAW_TABLE" for r in results),
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}")
    return 0 if payload["all_success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
