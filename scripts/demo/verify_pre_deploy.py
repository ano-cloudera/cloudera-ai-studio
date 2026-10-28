#!/usr/bin/env python3
"""Pre-deploy verification: core pytest + MCP smoke. Exit 0 when deploy-safe."""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001").rstrip("/")


def _http_json(path: str, *, method: str = "GET", body: dict | None = None) -> tuple[int, dict | str]:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{API}{path}", data=data, method=method, headers=headers)  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


def main() -> int:
    results: dict[str, str] = {}

    proc = subprocess.run(
        [str(ROOT / ".venv/bin/python"), "-m", "pytest", "tests/test_mcp_connector.py", "tests/test_mcp_chat_e2e.py", "-q"],
        cwd=ROOT / "backend",
        capture_output=True,
        text=True,
    )
    results["pytest_mcp"] = "PASS" if proc.returncode == 0 else f"FAIL\n{proc.stderr[-800:]}"

    st, health = _http_json("/health")
    results["backend_health"] = "PASS" if st == 200 else f"FAIL {st}"

    st, _ = _http_json("/api/v1/mcp/settings")
    results["mcp_settings_api"] = "PASS" if st == 200 else f"FAIL {st}"

    st, conn = _http_json("/api/v1/mcp/connectors")
    connectors = conn.get("connectors") if isinstance(conn, dict) else []
    results["mcp_connectors_api"] = "PASS" if st == 200 and connectors else f"FAIL {st}"

    cid = connectors[0]["id"] if connectors else "studio-demo"
    st, chat = _http_json(
        "/chat",
        method="POST",
        body={
            "session_id": "pre-deploy-mcp",
            "question": "What is our AI stack?",
            "provider": "gemini",
            "model": "mcp-no-llm",
            "context_sources": [{"type": "mcp_connector", "id": cid, "name": "MCP"}],
        },
    )
    ok_chat = st == 200 and isinstance(chat, dict) and chat.get("strategy") == "mcp" and chat.get("status") == "SUCCESS"
    results["mcp_chat_live"] = "PASS" if ok_chat else f"FAIL http={st} body={chat!s:.200}"

    proc2 = subprocess.run(
        [sys.executable, str(ROOT / "scripts/demo/run_amp_accelerator_readiness.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    results["amp_readiness"] = "PASS" if proc2.returncode == 0 else "WARN (check bootstrap_validate)"

    all_ok = all(v == "PASS" or v.startswith("PASS") for k, v in results.items() if k != "amp_readiness")
    out = {"ok": all_ok, "api_base": API, "checks": results}
    print(json.dumps(out, indent=2))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
