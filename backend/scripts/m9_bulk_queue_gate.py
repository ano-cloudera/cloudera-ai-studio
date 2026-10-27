#!/usr/bin/env python3
"""Live browser gate: Knowledge bulk upload queue."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
import uuid
import urllib.request
from pathlib import Path

import httpx
import websockets.sync.client as ws_client

REPO = Path(__file__).resolve().parents[2]
EVID = REPO / "testing/evidence/post-uat/CHAT-CONTEXT-V1"
BASE = "http://127.0.0.1:3001"
BE = "http://127.0.0.1:8001"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
FIX = REPO / "backend/tests/fixtures/chat_attachments"


def main() -> int:
    name = f"M9 bulk closure {uuid.uuid4().hex[:8]}"
    lib = httpx.Client(base_url=BE, timeout=60).post(
        "/api/v1/libraries", json={"name": name, "description": "Disposable M9 browser closure"}
    ).json()["library"]
    files = [FIX / "sample.txt", FIX / "sample.md", FIX / "sample.pdf"]

    proc = subprocess.Popen(
        [
            CHROME,
            "--remote-debugging-port=9261",
            "--user-data-dir=/tmp/m9-bulk-queue-gate",
            "--remote-allow-origins=*",
            "--headless=new",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            f"{BASE}/knowledge",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(12)
        tabs = json.loads(urllib.request.urlopen("http://127.0.0.1:9261/json/list").read())
        page = next(t for t in tabs if t.get("type") == "page")
        ws = ws_client.connect(page["webSocketDebuggerUrl"], max_size=16 * 1024 * 1024)
        mid = 0

        def send(method: str, params: dict | None = None) -> dict:
            nonlocal mid
            mid += 1
            ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            while True:
                payload = json.loads(ws.recv())
                if payload.get("id") == mid:
                    return payload

        def val(expr: str):
            outer = send("Runtime.evaluate", {"expression": expr, "returnByValue": True}).get("result") or {}
            return (outer.get("result") or {}).get("value")

        send("Page.enable")
        send("Runtime.enable")
        time.sleep(3)
        val(
            f"""(() => {{
              const row = [...document.querySelectorAll('tr')].find(r => r.innerText.includes({json.dumps(name)}));
              row?.click();
              return !!row;
            }})()"""
        )
        time.sleep(3)
        doc = send("DOM.getDocument")["result"]["root"]["nodeId"]
        node = send("DOM.querySelector", {"nodeId": doc, "selector": 'input[type="file"]'})["result"]["nodeId"]
        send("DOM.setFileInputFiles", {"nodeId": node, "files": [str(p.resolve()) for p in files]})
        val("document.querySelector('input[type=file]')?.dispatchEvent(new Event('change',{bubbles:true}))")
        queue = False
        for _ in range(40):
            if val('!!document.querySelector(\'[data-testid="document-upload-queue"]\')') is True:
                queue = True
                break
            time.sleep(0.5)
        items = int(val('document.querySelectorAll(\'[data-testid="document-upload-item"]\').length') or 0)
        statuses = int(val('document.querySelectorAll(\'[data-testid="document-upload-status"]\').length') or 0)
        summary = val('!!document.querySelector(\'[data-testid="document-upload-summary"]\')') is True
        active = EVID / "BULK" / "final-upload-queue-active.png"
        active.parent.mkdir(parents=True, exist_ok=True)
        active.write_bytes(base64.b64decode(send("Page.captureScreenshot", {"format": "png"})["result"]["data"]))
        completed = False
        for _ in range(360):
            if val(
                """(() => {
                  const items = [...document.querySelectorAll('[data-testid="document-upload-status"]')];
                  return items.length >= 3 && items.every(el => /Ready|Failed/i.test(el.innerText));
                })()"""
            ):
                completed = True
                break
            time.sleep(0.5)
        complete = EVID / "BULK" / "final-upload-queue-complete.png"
        complete.write_bytes(base64.b64decode(send("Page.captureScreenshot", {"format": "png"})["result"]["data"]))
        out = {
            "Bulk multi-file selection": "PASS" if items >= 3 else "FAIL",
            "Upload queue visible": "PASS" if queue else "FAIL",
            "Per-file statuses visible": "PASS" if statuses >= 3 and summary else "FAIL",
            "Completion verified": "PASS" if completed else "FAIL",
            "KNOWLEDGE_BULK_QUEUE_LIVE_PASS": "PASS"
            if items >= 3 and queue and statuses >= 3 and summary and completed
            else "FAIL",
            "library_id": lib["id"],
            "library_name": name,
        }
        ws.close()
        print(json.dumps(out, indent=2))
        return 0 if out["KNOWLEDGE_BULK_QUEUE_LIVE_PASS"] == "PASS" else 1
    finally:
        proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
