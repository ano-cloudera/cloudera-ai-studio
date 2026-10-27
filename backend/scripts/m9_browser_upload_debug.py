#!/usr/bin/env python3
"""Debug chat file upload in browser (CDP)."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path

import websockets.sync.client as ws_client

REPO = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:3001"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
USER_DATA = Path("/tmp/m9-chrome-upload-debug")
PORT = 9223


def main() -> None:
    proc = subprocess.Popen(
        [
            CHROME,
            f"--remote-debugging-port={PORT}",
            f"--user-data-dir={USER_DATA}",
            "--no-first-run",
            "--no-default-browser-check",
            "--remote-allow-origins=*",
            f"--window-size=1440,900",
            BASE,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(2)
        tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list").read())
        page = next(
            (t for t in tabs if t.get("type") == "page" and "3001" in t.get("url", "")),
            next(t for t in tabs if t.get("type") == "page"),
        )
        print("tab:", page.get("url"))
        ws = ws_client.connect(page["webSocketDebuggerUrl"], max_size=32 * 1024 * 1024)
        mid = 0
        logs: list[str] = []

        def send(method: str, params: dict | None = None) -> dict:
            nonlocal mid
            mid += 1
            ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            while True:
                payload = json.loads(ws.recv())
                if payload.get("method") == "Log.entryAdded":
                    entry = payload.get("params", {}).get("entry", {})
                    logs.append(f"[{entry.get('level')}] {entry.get('text')}")
                if payload.get("method") == "Network.responseReceived":
                    resp = payload.get("params", {}).get("response", {})
                    if "attachments/batch" in resp.get("url", ""):
                        logs.append(f"HTTP batch upload status={resp.get('status')}")
                if payload.get("id") == mid:
                    return payload

        def eval_value(expression: str) -> str:
            payload = send("Runtime.evaluate", {"expression": expression, "returnByValue": True})
            if payload.get("error"):
                print("EVAL ERR:", payload["error"])
            if "exceptionDetails" in payload:
                print("EVAL EXC:", payload["exceptionDetails"])
            result = payload.get("result") or {}
            val = result.get("value")
            if val is None and result.get("type") == "undefined":
                return ""
            return str(val) if val is not None else ""

        send("Runtime.enable")
        send("DOM.enable")
        send("Page.enable")
        send("Log.enable")
        send("Network.enable")
        send("Page.navigate", {"url": BASE})
        time.sleep(3)
        print("url:", eval_value("location.href"))
        print("title:", eval_value("document.title"))

        deadline = time.time() + 90
        while time.time() < deadline:
            if eval_value('!!document.querySelector(\'[aria-label="Add context or files"]\')') == "True":
                break
            time.sleep(0.5)
        else:
            print("TIMEOUT: composer + button never appeared")
            print("body snippet:", eval_value("(document.body?.innerText || '').slice(0,500)"))
            return

        eval_value('document.querySelector(\'[aria-label="Add context or files"]\')?.click()')
        time.sleep(0.4)
        print("menu click upload:", eval_value(
            "[...document.querySelectorAll('[role=menuitem]')].find(e=>e.textContent?.includes('Upload'))?.click() || 'missing'"
        ))
        sample = str((REPO / "backend/tests/fixtures/chat_attachments/sample.txt").resolve())
        doc = send("DOM.getDocument")["result"]["root"]["nodeId"]
        node_id = send("DOM.querySelector", {"nodeId": doc, "selector": 'input[type="file"]'})["result"].get("nodeId")
        print("file input nodeId:", node_id)
        if not node_id:
            return
        send("DOM.setFileInputFiles", {"nodeId": node_id, "files": [sample]})
        print(
            "dispatch change:",
            eval_value(
                "(() => { const i=document.querySelector('input[type=file]'); i?.dispatchEvent(new Event('change',{bubbles:true})); return i?.files?.length ?? 0; })()"
            ),
        )

        for i in range(30):
            time.sleep(1)
            text = eval_value("(document.body?.innerText || '')")
            print(f"--- tick {i} ---")
            for line in text.splitlines():
                low = line.lower()
                if any(k in low for k in ("sample.txt", "ready", "processing", "upload", "unsupported", "unable")):
                    print(" ", line[:120])
            if "Ready" in text or "Processing failed" in text:
                break
        if logs:
            print("--- console/network ---")
            for line in logs[-20:]:
                print(line)
    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    main()
