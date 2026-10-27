#!/usr/bin/env python3
"""Standalone Cloudera AI Studio browser smoke (CDP) — new repo stack only."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import httpx
import websockets.sync.client as ws_client

REPO = Path(__file__).resolve().parents[2]
EVID = REPO / "testing/evidence/standalone/BROWSER_SMOKE"
BASE = "http://127.0.0.1:3001"
API = "http://127.0.0.1:8001"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9255
BACKEND_SH = REPO / "scripts/dev-backend.sh"
FATAL_CONSOLE = (
    "uncaught (in promise)",
    "chunkloaderror",
    "application error",
    "hydration failed",
    "cannot read properties of null",
)


def curl_status(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return int(r.status)
    except (urllib.error.URLError, TimeoutError):
        return 0


def curl_ok(url: str) -> bool:
    return curl_status(url) == 200


def wait_http_stack(timeout: float = 120.0) -> dict[str, int | str]:
    """Wait until backend + frontend HTTP gates are green before CDP."""
    checks = {
        "be_health": f"{API}/health",
        "be_ready": f"{API}/health/ready",
        "fe_root": f"{BASE}/",
        "fe_knowledge": f"{BASE}/knowledge",
    }
    deadline = time.time() + timeout
    last: dict[str, int | str] = {}
    while time.time() < deadline:
        last = {k: curl_status(url) for k, url in checks.items()}
        if all(v == 200 for v in last.values()):
            last["stack_http"] = "PASS"
            return last
        time.sleep(0.75)
    last["stack_http"] = "FAIL"
    return last


def ensure_frontend() -> bool:
    if curl_ok(BASE):
        return True
    fe_log = REPO / ".tmp" / "frontend-3001-smoke.log"
    fe_log.parent.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        ["npm", "run", "dev", "--", "-p", "3001"],
        cwd=str(REPO / "frontend"),
        stdout=fe_log.open("w"),
        stderr=subprocess.STDOUT,
    )
    for _ in range(60):
        if curl_ok(BASE):
            return True
        time.sleep(1)
    return curl_ok(BASE)


def ensure_backend() -> bool:
    if curl_ok(f"{API}/health/ready"):
        return True
    if BACKEND_SH.is_file():
        subprocess.run([str(BACKEND_SH), "start"], cwd=str(REPO), check=False)
        for _ in range(60):
            if curl_ok(f"{API}/health/ready"):
                return True
            time.sleep(0.5)
    return curl_ok(f"{API}/health/ready")


def main() -> int:
    EVID.mkdir(parents=True, exist_ok=True)
    gates: dict[str, str] = {}

    if not ensure_backend():
        print(json.dumps({"status": "STANDALONE_BROWSER_SMOKE_BLOCKED", "blocker": "backend_not_ready"}, indent=2))
        return 1
    if not ensure_frontend():
        print(json.dumps({"status": "STANDALONE_BROWSER_SMOKE_BLOCKED", "blocker": "frontend_not_ready"}, indent=2))
        return 1

    http_gates = wait_http_stack()
    if http_gates.get("stack_http") != "PASS":
        print(
            json.dumps(
                {"status": "STANDALONE_BROWSER_SMOKE_BLOCKED", "blocker": "stack_http_not_ready", "http": http_gates},
                indent=2,
            )
        )
        return 1

    routes = [
        ("/", "ask_data"),
        ("/knowledge", "knowledge"),
        ("/semantic-layer", "semantic_layer"),
        ("/connectors", "data_sources"),
        ("/prompts", "prompts"),
        ("/skills", "skills"),
        ("/usage", "usage"),
        ("/settings", "settings"),
    ]

    profile = f"/tmp/cai-standalone-smoke-{uuid.uuid4().hex[:8]}"
    proc = subprocess.Popen(
        [
            CHROME,
            f"--remote-debugging-port={PORT}",
            f"--user-data-dir={profile}",
            "--remote-allow-origins=*",
            "--headless=new",
            "--window-size=1440,900",
            f"{BASE}/",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        time.sleep(3)
        tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=8).read())
        page = next(t for t in tabs if t.get("type") == "page")
        ws = ws_client.connect(page["webSocketDebuggerUrl"], max_size=32 * 1024 * 1024)
        mid = 0
        console_errors: list[str] = []

        def send(method: str, params: dict | None = None) -> dict:
            nonlocal mid
            mid += 1
            ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            while True:
                payload = json.loads(ws.recv())
                if payload.get("method") == "Runtime.consoleAPICalled":
                    level = payload.get("params", {}).get("type", "")
                    if level in ("error", "warning"):
                        args = payload["params"].get("args") or []
                        text = " ".join(
                            str(a.get("value") or a.get("description") or "") for a in args
                        ).lower()
                        if any(x in text for x in FATAL_CONSOLE):
                            console_errors.append(text[:240])
                if payload.get("id") == mid:
                    return payload

        send("Log.enable")
        send("Runtime.enable")
        send("Network.enable")
        send("Page.enable")

        def val(expression: str):
            outer = send(
                "Runtime.evaluate",
                {"expression": expression, "returnByValue": True, "awaitPromise": True},
            ).get("result") or {}
            inner = outer.get("result") or {}
            return inner.get("value")

        def wait_true(expr: str, timeout: float = 45.0) -> bool:
            deadline = time.time() + timeout
            while time.time() < deadline:
                if val(expr) is True:
                    return True
                time.sleep(0.4)
            return False

        # Hydration: AppShell nav + main content before route matrix.
        send("Page.navigate", {"url": f"{BASE}/"})
        hydration_ok = wait_true(
            """
            (() => {
              const nav = document.querySelector('nav') || document.querySelector('aside');
              const main = document.querySelector('main') || document.body;
              const textLen = (main?.innerText || '').length;
              return !!nav && textLen > 80 && document.readyState === 'complete';
            })()
            """,
            120,
        )
        gates["hydration_readiness"] = "PASS" if hydration_ok else "FAIL"
        if not hydration_ok:
            status = "STANDALONE_BROWSER_SMOKE_BLOCKED"
            out = {
                "status": status,
                "gates": gates,
                "http_gates": http_gates,
                "console_errors": console_errors[:10],
                "evidence_dir": str(EVID),
            }
            (EVID / "standalone_browser_smoke.json").write_text(json.dumps(out, indent=2))
            print(json.dumps(out, indent=2))
            return 1

        for path, key in routes:
            send("Page.navigate", {"url": f"{BASE}{path}"})
            ok = wait_true("(document.body?.innerText?.length || 0) > 40", 60)
            gates[f"route_{key}"] = "PASS" if ok else "FAIL"
            (EVID / f"{key}.png").write_bytes(
                base64.b64decode(
                    ((send("Page.captureScreenshot", {"format": "png"}) or {}).get("result") or {}).get("data") or ""
                )
                or b""
            )

        # Critical controls
        send("Page.navigate", {"url": f"{BASE}/"})
        gates["ask_composer"] = "PASS" if wait_true(
            '!!document.querySelector(\'textarea\') || !!document.querySelector(\'[data-testid="chat-composer"]\')',
            90,
        ) else "FAIL"

        send("Page.navigate", {"url": f"{BASE}/knowledge"})
        gates["knowledge_table"] = "PASS" if wait_true(
            "document.body.innerText.toLowerCase().includes('library') || !!document.querySelector('table')",
            90,
        ) else "FAIL"

        send("Page.navigate", {"url": f"{BASE}/semantic-layer"})
        gates["semantic_overview"] = "PASS" if wait_true(
            'document.body.innerText.includes("Overview") || !!document.querySelector(\'[data-testid="semantic-create-model"]\')',
            120,
        ) else "FAIL"

        for path, key, expr in (
            (
                "/connectors",
                "connectors_table",
                "document.body.innerText.toLowerCase().includes('data source') || document.body.innerText.toLowerCase().includes('connector')",
            ),
            ("/prompts", "prompts_table", "document.body.innerText.toLowerCase().includes('prompt')"),
            ("/skills", "skills_table", "document.body.innerText.toLowerCase().includes('skill')"),
        ):
            send("Page.navigate", {"url": f"{BASE}{path}"})
            gates[key] = "PASS" if wait_true(expr, 90) else "FAIL"

        gates["console_fatal"] = "PASS" if not console_errors else "FAIL"
        ws.close()

        with httpx.Client(base_url=API, timeout=30.0) as client:
            api_checks = {
                "semantic_models": client.get("/api/v1/semantic/models").status_code,
                "libraries": client.get("/api/v1/libraries").status_code,
                "prompts": client.get("/api/v1/prompts").status_code,
                "skills": client.get("/api/v1/skills").status_code,
                "connectors": client.get("/api/v1/connectors").status_code,
            }
        gates["api_smoke"] = "PASS" if all(c == 200 for c in api_checks.values()) else "FAIL"

        status = "STANDALONE_BROWSER_SMOKE_PASS" if all(v == "PASS" for v in gates.values()) else "STANDALONE_BROWSER_SMOKE_BLOCKED"
        out = {
            "status": status,
            "gates": gates,
            "http_gates": http_gates,
            "console_errors": console_errors[:10],
            "api_checks": api_checks,
            "evidence_dir": str(EVID),
        }
        (EVID / "standalone_browser_smoke.json").write_text(json.dumps(out, indent=2))
        print(json.dumps(out, indent=2))
        return 0 if status.endswith("_PASS") else 1
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == "__main__":
    sys.exit(main())
