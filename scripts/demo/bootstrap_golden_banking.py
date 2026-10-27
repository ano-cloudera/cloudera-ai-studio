#!/usr/bin/env python3
"""Idempotent Golden Banking demo bootstrap (local CAI sim or deployed Backend).

Set GOLDEN_PATH_API_BASE to the Backend URL (e.g. https://backend-service:8001).
Does not hardcode localhost; defaults to http://127.0.0.1:8001 for dev only.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "demo"))

from golden_e2e_common import (  # noqa: E402
    EVIDENCE,
    ROOT as REPO,
    backend_ready,
    http,
    metadata_snapshot,
    qdrant_ready,
    run_script,
    sim_db_path,
)

STEPS = (
    ("verify_banking_seed", "scripts/demo/seed_banking_postgres.py", []),
    ("banking_connector", "register_banking_connector.py", []),
    ("banking_knowledge", "register_banking_knowledge.py", []),
    ("banking_semantic", "register_banking_semantic.py", []),
)


def _dry_run() -> int:
    plan = {
        "mode": "dry-run",
        "steps": [name for name, _, _ in STEPS],
        "requires": {
            "backend_ready": backend_ready(),
            "qdrant_ready": qdrant_ready(),
            "sqlite": str(sim_db_path()),
        },
    }
    print(json.dumps(plan, indent=2))
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "bootstrap-plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return 0


def _apply() -> int:
    if not backend_ready():
        print("backend not ready on :8001 — start ./scripts/dev-cai-sim-backend.sh start", file=sys.stderr)
        return 1
    if not qdrant_ready():
        print("Qdrant not reachable — Knowledge bootstrap will fail", file=sys.stderr)
        return 1

    os.environ.setdefault("BANKING_DEMO_PG_PASSWORD", os.environ.get("M1PASS", "m1pass"))
    results: dict[str, dict] = {"steps": []}
    seed_report_path = REPO / "testing/evidence/golden-path/banking-data/seed-validation.json"
    seed_ok = False
    if seed_report_path.is_file():
        report = json.loads(seed_report_path.read_text(encoding="utf-8"))
        seed_ok = (
            240 <= int(report.get("customers", 0)) <= 260
            and 950 <= int(report.get("transactions", 0)) <= 1050
            and int(report.get("orphan_transactions", 1)) == 0
        )
    results["steps"].append({"step": "verify_banking_seed", "code": 0 if seed_ok else 1})
    if not seed_ok:
        export = seed_report_path
        export.parent.mkdir(parents=True, exist_ok=True)
        seed_apply = subprocess.run(
            [
                sys.executable,
                str(REPO / "scripts/demo/seed_banking_postgres.py"),
                "--apply",
                "--export-validation",
                str(export),
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        results["steps"].append({"step": "seed_banking_apply", "code": seed_apply.returncode})
        if seed_apply.returncode != 0:
            print(seed_apply.stderr, file=sys.stderr)
            return 1

    for name, script, _ in STEPS[1:]:
        code, detail = run_script(script)
        results["steps"].append({"step": name, "code": code, "detail": detail})
        if code != 0:
            print(f"bootstrap failed at {name}", detail, file=sys.stderr)
            EVIDENCE.mkdir(parents=True, exist_ok=True)
            (EVIDENCE / "bootstrap-apply.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
            return 1

    results["metadata"] = metadata_snapshot()
    ready_code, ready = http("GET", "/health/ready")
    results["platform_ready"] = ready_code == 200 and isinstance(ready, dict) and ready.get("core_ready") is True
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "bootstrap-apply.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "platform_ready": results["platform_ready"]}, indent=2))
    return 0 if results["platform_ready"] else 1


def _validate() -> int:
    checks = {
        "backend_ready": backend_ready(),
        "qdrant_ready": qdrant_ready(),
        "sqlite_exists": sim_db_path().is_file(),
        "connector_registration": (REPO / "testing/evidence/golden-path/PHASE1/connector-registration.json").is_file(),
        "knowledge_registration": (REPO / "testing/evidence/golden-path/PHASE2-KNOWLEDGE/library-registration.json").is_file(),
        "semantic_registration": (REPO / "testing/evidence/golden-path/PHASE3-SEMANTIC/semantic-registration.json").is_file(),
    }
    if checks["connector_registration"]:
        conn = json.loads((REPO / "testing/evidence/golden-path/PHASE1/connector-registration.json").read_text())
        cid = conn.get("connector_id")
        if cid:
            st, body = http("POST", f"/api/v1/connectors/{cid}/test")
            checks["connector_test"] = st == 200 and isinstance(body, dict) and body.get("status") == "SUCCESS"
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "bootstrap-validate.json").write_text(json.dumps(checks, indent=2) + "\n", encoding="utf-8")
    ok = all(v is True for v in checks.values())
    print(json.dumps({"ok": ok, "checks": checks}, indent=2))
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Golden Banking bootstrap orchestrator")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    group.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        return _dry_run()
    if args.apply:
        return _apply()
    return _validate()


if __name__ == "__main__":
    raise SystemExit(main())
