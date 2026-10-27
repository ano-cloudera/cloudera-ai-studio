#!/usr/bin/env python3
"""Phase 3 Semantic UI & Chat closure gate."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "testing" / "evidence" / "golden-path" / "PHASE3-SEMANTIC"
BROWSER = EVIDENCE / "browser"


def _run(script: str) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "demo" / script)],
        cwd=ROOT,
        env={**os.environ, "BANKING_DEMO_PG_PASSWORD": os.environ.get("BANKING_DEMO_PG_PASSWORD", "m1pass")},
        capture_output=True,
        text=True,
    )
    tail = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, tail.strip()[-400:]


def _pytest(*paths: str) -> tuple[bool, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "backend")
    env["GOLDEN_BANKING_RUN_INTEGRATION"] = "1"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *paths, "-q"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    gates: dict[str, str] = {}
    blockers: list[str] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        gates[name] = "PASS" if ok else "FAIL"
        if not ok:
            blockers.append(f"{name}: {detail}" if detail else name)

    chat_ok, chat_detail = _run("phase3_chat_governed_evidence.py")
    record("Real /chat governed semantic route", chat_ok, chat_detail)

    tier_ok, tier_detail = _run("banking_ask_tier_evidence.py")
    record("Ask Data tier matrix + guardrails", tier_ok, tier_detail)
    tier_path = EVIDENCE / "banking-ask-tier-matrix.json"
    if tier_path.is_file():
        tier = json.loads(tier_path.read_text(encoding="utf-8"))
        for key in (
            "tier1_active_customers",
            "tier1_active_customers_id",
            "tier2_by_channel",
            "tier3_rank_segments",
            "guardrail_python_ml",
        ):
            record(f"Tier scenario {key}", (tier.get("scenarios") or {}).get(key, {}).get("ok") is True)
    if (EVIDENCE / "chat-governed-evidence.json").is_file():
        chat = json.loads((EVIDENCE / "chat-governed-evidence.json").read_text())
        for key, label in (
            ("total_amount", "Governed total amount"),
            ("by_channel", "Governed by channel"),
            ("segment_join", "Governed customer segment join"),
            ("failed_rate", "Failed Transaction Rate"),
            ("active_customers", "Active Customers"),
        ):
            record(label, (chat.get("scenarios") or {}).get(key, {}).get("ok") is True)
        sample = (chat.get("scenarios") or {}).get("total_amount") or {}
        record("Correct Banking PostgreSQL binding", sample.get("connector_type") == "postgres")
        record("No Impala/legacy fallback", sample.get("context_mode") == "GOVERNED_SEMANTIC")

    rb_ok, rb_detail = _run("phase3_semantic_rollback_evidence.py")
    record("Version 2 created/published", rb_ok, rb_detail)
    if (EVIDENCE / "rollback-evidence.json").is_file():
        rb = json.loads((EVIDENCE / "rollback-evidence.json").read_text())
        record("Real rollback to Version 1", rb.get("rollback_result", {}).get("result") == "ROLLED_BACK")
        record("Post-rollback governed Ask", rb.get("chat_post_rollback_ok") is True)
        record("Runtime/deployment follows rollback", (rb.get("runtime_after_rollback") or {}).get("runtime_active_version") == 1)
        record("Final intended version explicit", rb.get("final_intended_active") == "runtime_deployment_v1")

    browser_ok, browser_detail = _run("phase3_semantic_browser_evidence.py")
    required_shots = [f"{c}-{'semantic-overview' if c=='A' else ''}" for c in "ABCDEFGHIJKLM"]
    # validate manifest
    manifest = BROWSER / "browser-evidence-manifest.json"
    png_ok = all((BROWSER / n).is_file() for n in (
        "A-semantic-overview.png", "B-data-models.png", "C-relationship.png", "D-metrics.png",
        "E-dimensions.png", "F-model-health.png", "G-publish-active.png", "H-governed-total-amount.png",
        "I-governed-by-channel.png", "J-governed-segment-join.png", "K-raw-vs-governed.png",
        "L-knowledge-vs-semantic-failed-rate.png", "M-version-history.png",
    ))
    record("Browser A–M evidence", browser_ok and png_ok, browser_detail)

    p3_chat, _ = _pytest(
        "backend/tests/test_golden_banking_phase3_chat.py",
        "backend/tests/test_golden_banking_phase3_semantic.py",
    )
    record("Semantic automated tests", p3_chat)

    for gate_script, label in (
        ("golden_path_banking_phase1_gate.py", "Golden Phase 1"),
        ("golden_path_banking_phase2_knowledge_gate.py", "Golden Phase 2"),
        ("golden_path_banking_phase3_semantic_gate.py", "Golden Phase 3"),
    ):
        proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "demo" / gate_script)], cwd=ROOT, env=os.environ.copy())
        record(label, proc.returncode == 0)

    proc = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    record("enterprise-ai-poc untouched", not any("enterprise-ai-poc" in l for l in proc.stdout.splitlines()))

    out = {"gates": gates, "blockers": blockers}
    (EVIDENCE / "phase3-closure-gate-report.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    if blockers:
        print("\nPHASE3_SEMANTIC_FINAL_UI_AND_CHAT_CLOSURE_BLOCKED")
        for b in blockers:
            print(f"  - {b}")
        return 1
    print("\nPHASE3_SEMANTIC_FINAL_UI_AND_CHAT_CLOSURE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
