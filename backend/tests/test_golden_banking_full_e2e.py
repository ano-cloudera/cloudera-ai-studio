"""Golden Banking full E2E helper tests (orchestration lives in scripts/demo)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVID = ROOT / "testing" / "evidence" / "golden-path" / "FULL-E2E"


def test_full_e2e_bootstrap_validate_script_exists():
    assert (ROOT / "scripts/demo/bootstrap_golden_banking.py").is_file()


def test_full_e2e_api_evidence_structure_when_present():
    path = EVID / "api-e2e-evidence.json"
    if not path.is_file():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload.get("data_source", {}).get("ok") is True
    assert payload.get("chat", {}).get("governed_all_ok") is True
