#!/usr/bin/env python3
"""Local AMP accelerator readiness gate (bootstrap validate + profile + tests + optional live UAT)."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "testing" / "evidence" / "golden-path" / "AMP-READINESS"
PY = ROOT / ".venv" / "bin" / "python"
sys.path.insert(0, str(ROOT / "scripts" / "demo"))

from golden_e2e_common import backend_ready, http, qdrant_ready  # noqa: E402


def _run(script: str, extra: list[str] | None = None) -> tuple[bool, str]:
    cmd = [str(PY), str(ROOT / "scripts" / "demo" / script), *(extra or [])]
    proc = subprocess.run(cmd, cwd=ROOT, env=os.environ.copy(), capture_output=True, text=True)
    detail = (proc.stderr or proc.stdout or "").strip()[-800:]
    return proc.returncode == 0, detail


def _pytest(relpath: str) -> bool:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "backend")
    proc = subprocess.run(
        [str(PY), "-m", "pytest", relpath, "-q", "--tb=no"],
        cwd=ROOT / "backend",
        env=env,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="AMP accelerator readiness gate")
    parser.add_argument("--apply-profile", action="store_true", help="Apply accelerator demo Ask Data preset")
    parser.add_argument("--apply-bootstrap", action="store_true", help="Run bootstrap_golden_banking.py --apply")
    parser.add_argument("--live-uat", action="store_true", help="Run 10q robustness + English memory UAT (needs LLM)")
    parser.add_argument("--patch-semantic", action="store_true", help="Run banking semantic publish-readiness patch")
    args = parser.parse_args()

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    gates: dict[str, str] = {}
    blockers: list[str] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        gates[name] = "PASS" if ok else "FAIL"
        if not ok:
            blockers.append(f"{name}: {detail}" if detail else name)

    record("backend_health", backend_ready())
    ready_st, ready = http("GET", "/health/ready")
    record(
        "platform_ready",
        ready_st == 200 and isinstance(ready, dict) and ready.get("core_ready") is True,
        str(ready)[:200],
    )
    record("qdrant_reachable", qdrant_ready())

    record("pytest_banking_catalog", _pytest("tests/test_banking_demo_catalog.py"))
    record("pytest_registry_resolver", _pytest("tests/test_semantic_registry_catalog_resolver.py"))

    if args.patch_semantic:
        ok, detail = _run("patch_banking_semantic_publish_readiness.py")
        record("patch_banking_semantic", ok, detail)

    if args.apply_bootstrap:
        ok, detail = _run("bootstrap_golden_banking.py", ["--apply"])
        record("bootstrap_golden_banking", ok, detail)
    else:
        ok, _ = _run("bootstrap_golden_banking.py", ["--validate"])
        record("bootstrap_validate", ok)

    if args.apply_profile:
        ok, detail = _run("apply_accelerator_demo_profile.py")
        record("accelerator_demo_profile", ok, detail)
    else:
        st, pres = http("GET", "/api/v1/ask-data/presentation-config?workspace_slug=default")
        tier1_narr = (
            isinstance(pres, dict)
            and (pres.get("presentation") or {}).get("tier1_show_narrative") is True
        )
        record("demo_profile_tier1_narrative", tier1_narr, "enable with --apply-profile")

    if args.live_uat:
        ok, detail = _run("banking_robustness_10q.py")
        record("banking_robustness_10q", ok, detail)
        ok, detail = _run("banking_uat_english_memory_3q.py")
        record("banking_uat_english_memory_3q", ok, detail)

    summary = {
        "ok": not blockers,
        "gates": gates,
        "blockers": blockers,
        "next": [
            "docs/deployment/AMP_ACCELERATOR_PLAYBOOK.md",
            "docs/deployment/CAI_REAL_DEPLOYMENT_CHECKLIST.md",
            "deployment/amp/README.md",
        ],
    }
    (EVIDENCE / "readiness-gate.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
