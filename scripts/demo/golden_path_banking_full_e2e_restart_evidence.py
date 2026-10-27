#!/usr/bin/env python3
"""Full E2E restart persistence evidence (backend, Qdrant, frontend, full stack)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "demo"))

from golden_e2e_common import (  # noqa: E402
    EVIDENCE,
    backend_ready,
    http,
    metadata_snapshot,
    qdrant_ready,
    run_script,
    shell,
    wait_http_ok,
)

OUT = EVIDENCE / "restart-evidence.json"
SESSION_MARK = "golden-e2e-restart-session"


def _rag_probe(library_id: str) -> bool:
    st, body = http(
        "POST",
        "/api/v1/retrieval/search",
        {"query": "Failed Transaction Rate definition", "library_ids": [str(library_id)], "top_k": 5},
    )
    return st == 200 and isinstance(body, dict) and len(body.get("results") or []) > 0


def _governed_probe() -> bool:
    code, _ = run_script("phase3_chat_governed_evidence.py", timeout=240.0)
    return code == 0


def _try_qdrant_restart() -> dict:
    attempts = [
        ["docker", "restart", "qdrant"],
        ["docker", "restart", "accelerator-qdrant"],
        ["docker", "compose", "restart", "qdrant"],
    ]
    for cmd in attempts:
        code, detail = shell(cmd, timeout=120.0)
        if code == 0:
            time.sleep(3)
            return {"restarted": True, "cmd": cmd, "ready": qdrant_ready()}
    return {"restarted": False, "ready_before_after": qdrant_ready(), "note": "No Qdrant container restart command succeeded; RAG re-probed only."}


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if not backend_ready():
        print("backend not ready", file=sys.stderr)
        return 1

    lib_path = ROOT / "testing/evidence/golden-path/PHASE2-KNOWLEDGE/library-registration.json"
    library_id = json.loads(lib_path.read_text())["library_id"] if lib_path.is_file() else None

    evidence: dict = {"phases": []}
    evidence["before"] = metadata_snapshot()

    # Seed chat session marker via governed chat script session (sqlite messages)
    _governed_probe()
    mid = metadata_snapshot()
    evidence["after_chat"] = mid

    # Backend restart
    shell(["./scripts/dev-cai-sim-backend.sh", "stop"])
    time.sleep(2)
    shell(["./scripts/dev-cai-sim-backend.sh", "start"], timeout=120.0)
    wait_http_ok("http://127.0.0.1:8001/health/ready", 120)
    time.sleep(3)
    after_backend = metadata_snapshot()
    backend_ok = (
        after_backend.get("connectors") == evidence["before"].get("connectors")
        and after_backend.get("libraries") == evidence["before"].get("libraries")
        and (after_backend.get("messages") or 0) >= (mid.get("messages") or 0)
    )
    evidence["phases"].append(
        {
            "name": "backend_restart",
            "metadata_preserved": backend_ok,
            "governed_after": _governed_probe(),
        }
    )

    # Qdrant restart / probe
    qdrant_phase = _try_qdrant_restart()
    rag_ok = _rag_probe(library_id) if library_id else False
    evidence["phases"].append({"name": "qdrant_restart", **qdrant_phase, "rag_ok": rag_ok})

    # Frontend restart
    fe_stop, _ = shell(["./scripts/dev-frontend.sh", "stop"])
    time.sleep(1)
    fe_start, _ = shell(["./scripts/dev-frontend.sh", "start"], timeout=120.0)
    fe_ok = wait_http_ok("http://127.0.0.1:3001/", 90)
    evidence["phases"].append({"name": "frontend_restart", "stop_code": fe_stop, "start_code": fe_start, "http_ok": fe_ok})

    # Full stack restart
    shell(["./scripts/dev-frontend.sh", "stop"])
    shell(["./scripts/dev-cai-sim-backend.sh", "stop"])
    time.sleep(2)
    _try_qdrant_restart()
    time.sleep(2)
    shell(["./scripts/dev-cai-sim-backend.sh", "start"], timeout=120.0)
    wait_http_ok("http://127.0.0.1:8001/health/ready", 120)
    time.sleep(3)
    shell(["./scripts/dev-frontend.sh", "start"], timeout=120.0)
    wait_http_ok("http://127.0.0.1:3001/", 90)
    stack_ok = backend_ready() and qdrant_ready() and _governed_probe() and (not library_id or _rag_probe(library_id))
    evidence["phases"].append({"name": "full_stack_restart", "ok": stack_ok})
    evidence["after"] = metadata_snapshot()
    evidence["session_mark"] = SESSION_MARK

    p0, p1, p2, p3 = evidence["phases"]
    evidence["ok"] = (
        p0.get("metadata_preserved") is True
        and p0.get("governed_after") is True
        and p1.get("rag_ok") is True
        and p2.get("http_ok") is True
        and p3.get("ok") is True
    )
    OUT.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": evidence["ok"], "path": str(OUT)}, indent=2))
    return 0 if evidence["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
