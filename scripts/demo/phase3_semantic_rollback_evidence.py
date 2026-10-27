#!/usr/bin/env python3
"""Phase 3 — controlled Version 2 publish + runtime rollback evidence."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "demo"))
from golden_banking_semantic_constants import MODEL_KEY  # noqa: E402

OUT = ROOT / "testing" / "evidence" / "golden-path" / "PHASE3-SEMANTIC" / "rollback-evidence.json"
API = os.environ.get("GOLDEN_PATH_API_BASE", "http://127.0.0.1:8001")
CHAT_SCRIPT = ROOT / "scripts/demo/phase3_chat_governed_evidence.py"
V1_DEPLOYMENT = os.environ.get(
    "GOLDEN_BANKING_V1_DEPLOYMENT_ID", "d4e15f94-1ef9-4742-85a3-329782022d3f"
)


def _http(method: str, path: str, body: dict | None = None) -> tuple[int, dict | str]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def _run_chat() -> bool:
    proc = subprocess.run(
        [sys.executable, str(CHAT_SCRIPT)],
        cwd=ROOT,
        env={**os.environ, "BANKING_DEMO_PG_PASSWORD": os.environ.get("BANKING_DEMO_PG_PASSWORD", "m1pass")},
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    st, models = _http("GET", "/api/v1/semantic/models")
    if st != 200:
        return 1
    model = next(m for m in models["models"] if m["key"] == MODEL_KEY)
    model_id = model["id"]

    _http("POST", f"/api/v1/semantic/runtime/deployments/{V1_DEPLOYMENT}/rollback", {})
    st, rt0 = _http("GET", f"/api/v1/semantic/runtime/status?model_key={MODEL_KEY}")
    if not _run_chat():
        print("baseline v1 chat failed", file=sys.stderr)
        return 1

    st, vers = _http("GET", f"/api/v1/semantic/models/{model_id}/versions")
    v1_version = next(
        (v for v in vers.get("versions") or [] if v.get("version_number") == 1),
        None,
    )
    if not v1_version:
        print("version 1 row missing", file=sys.stderr)
        return 1

    st, cloned = _http("POST", f"/api/v1/semantic/versions/{v1_version['id']}/clone")
    if st != 200:
        print("clone failed", cloned, file=sys.stderr)
        return 1
    draft_id = cloned["version"]["id"]

    st, terms = _http("GET", f"/api/v1/semantic/versions/{draft_id}/terms")
    term = next((t for t in terms.get("terms") or [] if t.get("key") == "transaction_attempt"), None)
    if term:
        _http(
            "PATCH",
            f"/api/v1/semantic/versions/{draft_id}/terms/{term['id']}",
            {"definition": (term.get("definition") or "").rstrip() + " (Version 2 glossary tweak.)"},
        )

    st, pub = _http("POST", f"/api/v1/semantic/models/{model_id}/publish-to-ask-data", {"version_id": draft_id})
    if st != 200:
        print("publish v2 failed", pub, file=sys.stderr)
        return 1

    st, rt2 = _http("GET", f"/api/v1/semantic/runtime/status?model_key={MODEL_KEY}")
    chat_v2_ok = _run_chat()

    st, rb = _http("POST", f"/api/v1/semantic/runtime/deployments/{V1_DEPLOYMENT}/rollback", {})
    if st != 200:
        print("rollback failed", rb, file=sys.stderr)
        return 1

    st, rt3 = _http("GET", f"/api/v1/semantic/runtime/status?model_key={MODEL_KEY}")
    chat_post_ok = _run_chat()

    evidence = {
        "version_1": {
            "version_number": 1,
            "version_id": v1_version["id"],
            "deployment_id": V1_DEPLOYMENT,
        },
        "version_2": {
            "version_id": pub.get("version_id"),
            "version_number": pub.get("version_number"),
            "deployment_id": pub.get("runtime_deployment_id"),
        },
        "runtime_baseline_v1": rt0,
        "runtime_after_v2": rt2,
        "runtime_after_rollback": rt3,
        "chat_v2_ok": chat_v2_ok,
        "chat_post_rollback_ok": chat_post_ok,
        "rollback_result": rb,
        "final_intended_active": "runtime_deployment_v1",
    }
    OUT.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    dep_after = (rt3.get("deployment") or {}).get("deployment_id")
    ok = (
        chat_v2_ok
        and chat_post_ok
        and dep_after == V1_DEPLOYMENT
        and rt3.get("runtime_active_version") == 1
    )
    print(json.dumps({"ok": ok, "path": str(OUT)}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
