#!/usr/bin/env python3
"""Capture M9 browser evidence via Chrome DevTools Protocol (local 3001)."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path

import websockets.sync.client as ws_client

REPO = Path(__file__).resolve().parents[2]
EVID = REPO / "testing/evidence/post-uat/CHAT-CONTEXT-V1"
BASE = "http://127.0.0.1:3001"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
USER_DATA = Path("/tmp/m9-chrome-evidence-profile")


def _page_tab(port: int) -> dict:
    tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list").read())
    return next(
        (t for t in tabs if t.get("type") == "page" and "3001" in t.get("url", "")),
        next(t for t in tabs if t.get("type") == "page"),
    )


def _cdp(ws_url: str):
    ws = ws_client.connect(ws_url, max_size=32 * 1024 * 1024)
    msg_id = 0

    def send(method: str, params: dict | None = None) -> dict:
        nonlocal msg_id
        msg_id += 1
        ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        while True:
            raw = ws.recv()
            payload = json.loads(raw)
            if payload.get("id") == msg_id:
                return payload

    return ws, send


def _remote_object(send, expression: str) -> dict:
    """Runtime.evaluate returns { result: { result: RemoteObject, exceptionDetails? } }."""
    response = send("Runtime.evaluate", {"expression": expression, "returnByValue": True})
    outer = response.get("result") or {}
    if outer.get("exceptionDetails"):
        return {"type": "exception", "value": str(outer["exceptionDetails"])}
    return outer.get("result") or {}


def _eval(send, expression: str) -> str:
    payload = _remote_object(send, expression)
    if payload.get("type") == "undefined":
        return ""
    value = payload.get("value")
    if value is None:
        return ""
    return str(value)


def _wait_eval(send, expression: str, *, timeout_s: float = 45.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        raw = _eval(send, expression)
        if raw.lower() in {"true", "1"}:
            return True
        time.sleep(0.5)
    return False


def _set_file_input(send, file_path: Path) -> None:
    doc = send("DOM.getDocument")["result"]["root"]["nodeId"]
    node_id = send("DOM.querySelector", {"nodeId": doc, "selector": 'input[type="file"]'})["result"]["nodeId"]
    send("DOM.setFileInputFiles", {"nodeId": node_id, "files": [str(file_path.resolve())]})


def _wait_text(send, needle: str, timeout_s: float = 45.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if needle in _eval(send, "document.body.innerText"):
            return True
        time.sleep(0.75)
    return False


def _screenshot(send, path: Path) -> None:
    result = send("Page.captureScreenshot", {"format": "png", "fromSurface": True})
    path.parent.mkdir(parents=True, exist_ok=True)
    import base64

    path.write_bytes(base64.b64decode(result["result"]["data"]))


def main() -> int:
    USER_DATA.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [
            CHROME,
            f"--remote-debugging-port=9222",
            f"--user-data-dir={USER_DATA}",
            "--no-first-run",
            "--no-default-browser-check",
            "--remote-allow-origins=*",
            "--headless=new",
            f"--window-size=1440,900",
            BASE,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(3)
        page = _page_tab(9222)
        ws, send = _cdp(page["webSocketDebuggerUrl"])
        send("Page.enable")
        send("Runtime.enable")
        send("DOM.enable")
        if "3001" not in page.get("url", ""):
            send("Page.navigate", {"url": BASE})
        time.sleep(15)
        if not _wait_eval(
            send,
            '!!document.querySelector(\'[data-testid="chat-composer"]\')',
            timeout_s=45.0,
        ):
            _screenshot(send, EVID / "ERRORS" / "01-composer-not-ready.png")
            debug = _eval(
                send,
                "JSON.stringify({url:location.href, err:document.body.innerText.includes('Application error'), composer:!!document.querySelector('[data-testid=\"chat-composer\"]'), add:!!document.querySelector('[data-testid=\"chat-add-button\"]'), input:!!document.querySelector('[data-testid=\"chat-input\"]')})",
            )
            print(json.dumps({"status": "FAIL", "reason": "composer_not_ready", "debug": debug}, indent=2))
            return 1
        time.sleep(1)
        _screenshot(send, EVID / "BROWSER" / "03-ask-data-loaded.png")

        send(
            "Runtime.evaluate",
            {
                "expression": """
(() => {
  const btn = document.querySelector('[aria-label="Add context or files"]');
  if (btn) { btn.click(); return 'clicked'; }
  return 'missing';
})()
""",
                "returnByValue": True,
            },
        )
        time.sleep(0.5)
        _screenshot(send, EVID / "BROWSER" / "04-composer-plus-menu.png")

        _eval(
            send,
            """
(() => {
  const item = [...document.querySelectorAll('[role="menuitem"]')].find(el => el.textContent?.includes('Upload files'));
  item?.click();
  return item ? 'upload' : 'missing';
})()
""",
        )
        sample_txt = REPO / "backend/tests/fixtures/chat_attachments/sample.txt"
        _set_file_input(send, sample_txt)
        _eval(
            send,
            """
(() => {
  const input = document.querySelector('input[type="file"]');
  input?.dispatchEvent(new Event('change', { bubbles: true }));
  return input ? 'changed' : 'missing-input';
})()
""",
        )
        time.sleep(0.5)
        _screenshot(send, EVID / "UPLOAD" / "01-upload-started.png")
        ready = _wait_text(send, "Ready", timeout_s=90.0)
        _screenshot(send, EVID / "UPLOAD" / "02-attachment-ready.png")
        if not ready:
            err_snip = _eval(
                send,
                "(document.body?.innerText || '').split('\\n').filter(l=>/error|unable|unsupported|failed/i.test(l)).slice(0,5).join(' | ')",
            )
            print(json.dumps({"upload_debug": err_snip}, indent=2))
        if ready:
            _eval(
                send,
                """
(() => {
  const btn = [...document.querySelectorAll('button')].find(b => b.textContent?.trim() === 'Save to Knowledge');
  btn?.click();
  return btn ? 'save' : 'missing';
})()
""",
            )
            time.sleep(1)
            _screenshot(send, EVID / "SAVE-TO-KNOWLEDGE" / "01-save-modal.png")

        send("Page.navigate", {"url": f"{BASE}/knowledge"})
        time.sleep(2)
        _screenshot(send, EVID / "BULK" / "01-knowledge-page.png")
        ws.close()
        print(
            json.dumps(
                {
                    "status": "PASS" if ready else "PARTIAL",
                    "upload_ready": ready,
                    "evidence_dir": str(EVID),
                },
                indent=2,
            )
        )
        return 0
    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
