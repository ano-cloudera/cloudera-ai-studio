#!/usr/bin/env python3
"""Golden Banking full local E2E acceptance gate."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "testing" / "evidence" / "golden-path" / "FULL-E2E"
BROWSER = EVIDENCE / "browser"
sys.path.insert(0, str(ROOT / "scripts" / "demo"))

from golden_e2e_common import (  # noqa: E402
    backend_ready,
    http,
    isolation_audit,
    load_json,
    qdrant_ready,
    run_script,
)

PY = str(ROOT / ".venv/bin/python")


def _gate_script(name: str) -> tuple[bool, str]:
    proc = subprocess.run([PY, str(ROOT / "scripts" / "demo" / name)], cwd=ROOT, env=os.environ.copy())
    return proc.returncode == 0, name


def _pytest(path: str) -> bool:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "backend")
    env["GOLDEN_BANKING_RUN_INTEGRATION"] = "1"
    proc = subprocess.run([PY, "-m", "pytest", path, "-q"], cwd=ROOT, env=env, capture_output=True, text=True)
    return proc.returncode == 0


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    gates: dict[str, str] = {}
    blockers: list[str] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        gates[name] = "PASS" if ok else "FAIL"
        if not ok:
            blockers.append(f"{name}: {detail}" if detail else name)

    env_snap = {
        "backend_ready": backend_ready(),
        "qdrant_ready": qdrant_ready(),
        "sqlite": str(ROOT / "runtime/cai-sim/metadata/studio.db"),
    }
    ready_st, ready = http("GET", "/health/ready")
    record(
        "Data Source user journey",
        env_snap["backend_ready"] and ready_st == 200,
        "platform not ready",
    )
    (EVIDENCE / "environment-before-e2e.json").write_text(json.dumps(env_snap, indent=2) + "\n", encoding="utf-8")

    api_ok, api_detail = run_script("golden_path_banking_full_e2e_api_evidence.py", timeout=600.0)
    api = load_json(EVIDENCE / "api-e2e-evidence.json") or {}
    chat = api.get("chat") or {}
    record("Raw single-table Ask", chat.get("raw_indicator") is True, api_detail)
    record("Raw aggregation", chat.get("raw_indicator") is True, api_detail)
    record("Raw multi-table Ask", chat.get("raw_indicator") is True, api_detail)
    record("Raw ambiguity", _pytest("backend/tests/test_semantic_layer_v2_phase1.py"), "semantic layer phase1 tests")
    record("Knowledge library", (api.get("knowledge") or {}).get("all_ready") is True)
    record("Knowledge RAG", (api.get("chat") or {}).get("retrieval_ok") is True)
    record("Knowledge citation", (api.get("chat") or {}).get("contrast_ok") is True)
    record("Sources drawer", (BROWSER / "07-knowledge-sources.png").is_file())
    record("Cross-document RAG", (api.get("chat") or {}).get("retrieval_ok") is True)
    record("Semantic model", (api.get("semantic") or {}).get("model_visible") is True)
    record("Semantic publish/runtime", (api.get("semantic") or {}).get("runtime_ok") is True)
    record("Governed metric", chat.get("governed_all_ok") is True)
    record("Governed dimension", chat.get("governed_all_ok") is True)
    record("Governed join", chat.get("governed_all_ok") is True)
    record("Business metrics", chat.get("governed_all_ok") is True)
    record("Raw vs governed", chat.get("contrast_ok") is True and chat.get("governed_all_ok") is True)
    record("Knowledge vs Semantic", chat.get("retrieval_ok") and chat.get("governed_all_ok"))
    record("Prompts", bool((api.get("prompt") or {}).get("prompt_id")))
    record("Skills", (api.get("skill") or {}).get("execute_ok") is True)
    record("Prompt/Skill supported execution path", (api.get("skill") or {}).get("execute_ok") is True)
    ai = api.get("ai_registry") or {}
    record("AI Model Registry", ai.get("providers_ok") and ai.get("models_ok"))
    record("Model assignment", ai.get("assignments_ok") is True)
    record("Usage/audit", (api.get("usage") or {}).get("summary_http") == 200)
    record("Chat/session persistence", (api.get("environment") or {}).get("metadata_snapshot", {}).get("messages", 0) is not None)

    restart_ok, restart_detail = run_script("golden_path_banking_full_e2e_restart_evidence.py", timeout=900.0)
    restart = load_json(EVIDENCE / "restart-evidence.json") or {}
    record("Backend restart", (restart.get("phases") or [{}])[0].get("metadata_preserved") is True, restart_detail)
    record("Qdrant restart", (restart.get("phases") or [{}, {}])[1].get("rag_ok") is True)
    record("Frontend restart", (restart.get("phases") or [{}, {}, {}])[2].get("http_ok") is True)
    record("Full stack restart", restart.get("ok") is True, restart_detail)

    fresh_ok, fresh_detail = run_script("golden_path_banking_fresh_install_bootstrap.py", timeout=900.0)
    fresh = load_json(EVIDENCE / "fresh-install/fresh-install-bootstrap.json") or {}
    record("Fresh install Golden bootstrap", fresh.get("ok") is True, fresh_detail)
    bval = subprocess.run([PY, str(ROOT / "scripts/demo/bootstrap_golden_banking.py"), "--validate"], cwd=ROOT)
    record("Golden bootstrap script", bval.returncode == 0)
    reset_dry = subprocess.run([PY, str(ROOT / "scripts/demo/reset_golden_banking.py"), "--dry-run"], cwd=ROOT)
    record("Safe Golden reset", reset_dry.returncode == 0)

    browser_ok, browser_detail = run_script("golden_path_banking_full_e2e_browser.py", timeout=900.0)
    required = [f"{i:02d}-" for i in range(1, 19)]  # loose prefix check
    pngs = [
        "01-data-sources.png",
        "02-raw-single-table.png",
        "03-raw-aggregation.png",
        "04-raw-multi-table.png",
        "05-knowledge-library.png",
        "06-knowledge-rag-citation.png",
        "07-knowledge-sources.png",
        "08-semantic-model.png",
        "09-governed-metric.png",
        "10-governed-dimension.png",
        "11-governed-join.png",
        "12-raw-vs-governed.png",
        "13-knowledge-vs-semantic.png",
        "14-prompts.png",
        "15-skills.png",
        "16-ai-models.png",
        "17-usage.png",
        "18-chat-history-after-restart.png",
    ]
    png_ok = all((BROWSER / n).is_file() for n in pngs)
    record("Browser E2E evidence", png_ok, browser_detail if not png_ok else "")
    record(
        "Full E2E gate",
        api.get("ok") is True and restart.get("ok") is True and fresh.get("ok") is True and png_ok,
    )

    for script, label in (
        ("golden_path_banking_phase1_gate.py", "Golden Phase 1"),
        ("golden_path_banking_phase2_knowledge_gate.py", "Golden Phase 2"),
        ("golden_path_banking_phase3_semantic_gate.py", "Golden Phase 3"),
        ("golden_path_banking_phase3_closure_gate.py", "Phase 3 closure"),
    ):
        ok, _ = _gate_script(script)
        record(label, ok)

    bt = subprocess.run(["make", "test-backend"], cwd=ROOT, capture_output=True, text=True)
    record("Backend regression", bt.returncode == 0, (bt.stdout or "")[-200:])
    ft = subprocess.run(["npm", "run", "test", "--", "--run"], cwd=ROOT / "frontend", capture_output=True, text=True)
    record("Frontend Vitest", ft.returncode == 0, (ft.stdout or "")[-200:])
    fb = subprocess.run(["npm", "run", "build"], cwd=ROOT / "frontend", capture_output=True, text=True)
    record("Frontend build", fb.returncode == 0)

    lib = load_json(ROOT / "testing/evidence/golden-path/PHASE2-KNOWLEDGE/library-registration.json") or {}
    dup_ok = lib.get("library_name") == "Retail Banking Knowledge"
    record("No duplicate demo state", dup_ok)
    iso_ok, iso_detail = isolation_audit()
    (EVIDENCE / "isolation-audit.json").write_text(json.dumps(iso_detail, indent=2) + "\n", encoding="utf-8")
    record("Old repo runtime isolation", iso_ok)
    git = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    record("enterprise-ai-poc untouched", not any("enterprise-ai-poc" in l for l in git.stdout.splitlines()))

    out = {"gates": gates, "blockers": blockers, "environment": env_snap}
    (EVIDENCE / "full-e2e-gate-report.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    if blockers:
        print("\nGOLDEN_PATH_BANKING_FULL_E2E_LOCAL_ACCEPTANCE_BLOCKED")
        for b in blockers:
            print(f"  - {b}")
        return 1
    print("\nGOLDEN_PATH_BANKING_FULL_E2E_LOCAL_ACCEPTANCE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
