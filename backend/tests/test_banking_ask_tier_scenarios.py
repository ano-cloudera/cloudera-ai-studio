"""Unit checks for Golden Banking Ask tier scenario evaluator."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "demo"))

from golden_banking_ask_scenarios import ASK_TIER_SCENARIOS, AskScenario, evaluate_scenario  # noqa: E402

requires_integration = pytest.mark.skipif(
    os.environ.get("GOLDEN_BANKING_RUN_INTEGRATION", "1") != "1",
    reason="Set GOLDEN_BANKING_RUN_INTEGRATION=1",
)


def test_guardrail_scenario_expects_unsupported():
    scenario = next(s for s in ASK_TIER_SCENARIOS if s.key == "guardrail_python_ml")
    body = {
        "status": "UNSUPPORTED",
        "presentation_tier": 1,
        "strategy": "unsupported",
        "data": {"row_count": 0, "rows": []},
    }
    ok, errors = evaluate_scenario(body, scenario)
    assert ok, errors


def test_tier1_kpi_scenario_accepts_kpi_chart():
    scenario = AskScenario(
        key="x",
        question="q",
        min_rows=1,
        max_rows=1,
        chart_types=("kpi", None),
        require_governed_sql=True,
        sql_must_contain=("COUNT",),
    )
    body = {
        "status": "SUCCESS",
        "presentation_tier": 1,
        "context_mode": "GOVERNED_SEMANTIC",
        "governed_sql": "SELECT COUNT(*) FROM t",
        "chart_spec": {"type": "kpi"},
        "data": {"row_count": 1, "rows": [{}], "connector_type": "postgres"},
    }
    ok, errors = evaluate_scenario(body, scenario)
    assert ok, errors


def test_evaluator_flags_missing_sql_token():
    scenario = AskScenario(
        key="y",
        question="q",
        require_governed_sql=True,
        sql_must_contain=("GROUP BY",),
    )
    body = {
        "status": "SUCCESS",
        "governed_sql": "SELECT 1",
        "data": {"row_count": 1, "connector_type": "postgres"},
        "context_mode": "GOVERNED_SEMANTIC",
    }
    ok, errors = evaluate_scenario(body, scenario)
    assert not ok
    assert any("GROUP BY" in e for e in errors)


@requires_integration
def test_banking_ask_tier_evidence_script():
    script = ROOT / "scripts/demo/banking_ask_tier_evidence.py"
    env = os.environ.copy()
    env.setdefault("BANKING_DEMO_PG_PASSWORD", "m1pass")
    proc = subprocess.run([sys.executable, str(script)], cwd=ROOT, env=env, capture_output=True, text=True)
    evidence = ROOT / "testing/evidence/golden-path/PHASE3-SEMANTIC/banking-ask-tier-matrix.json"
    if evidence.is_file():
        payload = json.loads(evidence.read_text(encoding="utf-8"))
        assert payload.get("all_ok") is True, payload
    assert proc.returncode == 0, proc.stderr[-1500:]
