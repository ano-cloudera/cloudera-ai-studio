"""Golden Path Banking Demo — Phase 3 (Semantic Layer)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "testing" / "evidence" / "golden-path" / "PHASE3-SEMANTIC"
REG = EVIDENCE / "semantic-registration.json"
API_EVIDENCE = EVIDENCE / "api-semantic-evidence.json"

requires_integration = pytest.mark.skipif(
    os.environ.get("GOLDEN_BANKING_RUN_INTEGRATION", "1") != "1",
    reason="Set GOLDEN_BANKING_RUN_INTEGRATION=1",
)


def _banking_pg_ok() -> bool:
    try:
        import psycopg

        with psycopg.connect(
            os.environ.get("BANKING_DEMO_URL", "postgresql://m1:m1pass@127.0.0.1:55432/banking_demo")
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception:
        return False


skip_no_banking = pytest.mark.skipif(not _banking_pg_ok(), reason="Banking PostgreSQL not reachable")


@requires_integration
@skip_no_banking
def test_phase3_registration_evidence_exists():
    assert REG.is_file(), "run scripts/demo/register_banking_semantic.py first"
    body = json.loads(REG.read_text(encoding="utf-8"))
    assert body.get("publish", {}).get("status") == "published"
    assert body.get("model_key") == "retail_banking_analytics"


@requires_integration
@skip_no_banking
def test_phase3_api_semantic_evidence():
    script = ROOT / "scripts/demo/phase3_api_semantic_evidence.py"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "backend")
    proc = subprocess.run([sys.executable, str(script)], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-800:]
    assert API_EVIDENCE.is_file()
    data = json.loads(API_EVIDENCE.read_text(encoding="utf-8"))
    assert all(data["registry_checks"].values())
    ask = data["governed_structured_ask"]
    assert ask["context_mode"] == "GOVERNED_SEMANTIC"
    assert ask["resolution_status"] == "resolved"
    raw = data["raw_postgres"]
    assert float(raw["total_transaction_amount"]) > 0
    assert float(raw["failed_transaction_rate"]) >= 0
    align = data["failed_rate_alignment"]
    assert "failed" in (align.get("glossary_definition") or "").casefold()
    assert "attempt" in (align.get("metric_business_definition") or "").casefold()


@requires_integration
def test_join_validation_ignores_sql_aliases():
    from app.semantic_registry.source_validators import extract_identifier_candidates

    idents = extract_identifier_candidates("a.customer_id = b.customer_id")
    assert "customer_id" in idents
    assert "a" in idents
