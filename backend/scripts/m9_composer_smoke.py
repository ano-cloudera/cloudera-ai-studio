#!/usr/bin/env python3
"""Composer readiness smoke (CDP) — gate before full M9 browser evidence."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import httpx
import websockets.sync.client as ws_client

BASE = "http://127.0.0.1:3001"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9241
USER_DATA = Path("/tmp/m9-composer-smoke-profile")
SCREENSHOT = (
    Path(__file__).resolve().parents[2]
    / "testing/evidence/post-uat/CHAT-CONTEXT-V1/ERRORS/composer-smoke-load.png"
)


def _remote_object(send, expression: str) -> dict:
    response = send("Runtime.evaluate", {"expression": expression, "returnByValue": True})
    outer = response.get("result") or {}
    return outer.get("result") or {}


def _eval_json(send, expression: str) -> dict:
    obj = _remote_object(send, expression)
    raw = obj.get("value")
    if isinstance(raw, str):
        return json.loads(raw)
    return {}


def main() -> int:
    api = httpx.Client(timeout=15.0)
    fe = api.get(BASE).status_code
    ready = api.get(f"{BASE}/api/health/ready").status_code
    models = api.get(f"{BASE}/api/models").status_code

    USER_DATA.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [
            CHROME,
            f"--remote-debugging-port={PORT}",
            f"--user-data-dir={USER_DATA}",
            "--remote-allow-origins=*",
            "--headless=new",
            "--window-size=1440,900",
            BASE,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    console_errors: list[str] = []
    failed_requests: list[str] = []
    try:
        time.sleep(12)
        tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list").read())
        page = next(t for t in tabs if t.get("type") == "page" and "3001" in t.get("url", ""))
        ws = ws_client.connect(page["webSocketDebuggerUrl"], max_size=16 * 1024 * 1024)
        mid = 0

        def send(method: str, params: dict | None = None) -> dict:
            nonlocal mid
            mid += 1
            ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            while True:
                payload = json.loads(ws.recv())
                if payload.get("method") == "Runtime.exceptionThrown":
                    exc = payload["params"]["exceptionDetails"]["exception"]
                    console_errors.append(str(exc.get("description") or exc)[:400])
                if payload.get("method") == "Network.responseReceived":
                    resp = payload["params"]["response"]
                    url = resp.get("url", "")
                    status = int(resp.get("status") or 0)
                    if status >= 400 and ("/api/" in url or "3001" in url):
                        failed_requests.append(f"{status} {url}")
                if payload.get("id") == mid:
                    return payload

        send("Runtime.enable")
        send("Network.enable")
        send("Page.enable")
        import base64

        cap = send("Page.captureScreenshot", {"format": "png", "fromSurface": True})
        SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
        SCREENSHOT.write_bytes(base64.b64decode(cap["result"]["data"]))

        dom = _eval_json(
            send,
            """JSON.stringify({
              composer: !!document.querySelector('[data-testid="chat-composer"]'),
              input: !!document.querySelector('[data-testid="chat-input"]'),
              add: !!document.querySelector('[data-testid="chat-add-button"]'),
              send: !!document.querySelector('[data-testid="chat-send-button"]'),
              inputDisabled: document.querySelector('[data-testid="chat-input"]')?.disabled ?? null,
              placeholder: document.querySelector('[data-testid="chat-input"]')?.placeholder ?? null,
              legacyPlusAria: !!document.querySelector('[aria-label="Add context or files"]'),
              appError: document.body.innerText.includes('Application error')
            })""",
        )
        ws.close()

        composer_ok = bool(dom.get("composer") and dom.get("input") and dom.get("add") and dom.get("send"))
        report = {
            "composer_rendered": "PASS" if composer_ok else "FAIL",
            "console_clean": "PASS" if not console_errors else "FAIL",
            "initial_network": "PASS" if not failed_requests else "FAIL",
            "old_selector_valid": "YES" if dom.get("legacyPlusAria") else "NO",
            "root_cause": "HARNESS" if composer_ok else "PRODUCT_OR_ENV",
            "composer_smoke": "PASS" if composer_ok and fe == 200 and ready == 200 else "FAIL",
            "fe_http": fe,
            "proxy_ready_http": ready,
            "models_http": models,
            "dom": dom,
            "console_errors": console_errors[:5],
            "failed_requests": failed_requests[:10],
            "screenshot": str(SCREENSHOT),
            "harness_note": "m9_browser_evidence previously read Runtime.evaluate at wrong CDP nesting level",
            "wait_selector": '[data-testid="chat-composer"]',
            "legacy_wait_selector": '[aria-label="Add context or files"]',
        }
        print(json.dumps(report, indent=2))
        return 0 if report["composer_smoke"] == "PASS" else 1
    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
