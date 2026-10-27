#!/usr/bin/env python3
"""Capture Knowledge V2.1 UX evidence (CDP, local :3001)."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websockets.sync.client as ws_client

REPO = Path(__file__).resolve().parents[2]
EVID = REPO / "testing/evidence/post-uat/KNOWLEDGE-V2-1"
BASE = "http://127.0.0.1:3001"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def main() -> int:
    EVID.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [
            CHROME,
            "--remote-debugging-port=9270",
            "--user-data-dir=/tmp/knowledge-v21-evidence",
            "--headless=new",
            "--disable-gpu",
            BASE + "/knowledge",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    results: dict[str, str] = {}
    try:
        time.sleep(12)
        tabs = json.loads(urllib.request.urlopen("http://127.0.0.1:9270/json/list").read())
        page = next(t for t in tabs if t.get("type") == "page")
        ws = ws_client.connect(page["webSocketDebuggerUrl"], max_size=8 * 1024 * 1024)
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

        def shot(name: str) -> None:
            data = send("Page.captureScreenshot", {"format": "png"})["result"]["data"]
            (EVID / name).write_bytes(base64.b64decode(data))

        send("Page.enable")
        for _ in range(60):
            if val('location.pathname.includes("knowledge")') is True:
                break
            time.sleep(0.5)
        time.sleep(2)
        default_cb = val('!!document.querySelector(\'table input[type=checkbox]\')')
        results["Default checkbox hidden"] = "PASS" if default_cb is not True else "FAIL"
        shot("landing-default.png")
        val('document.querySelector(\'[aria-label="Select libraries"]\')?.click()')
        time.sleep(0.5)
        sel_cb = val('!!document.querySelector(\'table input[type=checkbox]\')')
        results["Selection mode"] = "PASS" if sel_cb is True else "FAIL"
        shot("landing-selection-mode.png")
        val('document.querySelector(\'table input[type=checkbox][aria-label^="Select "]\')?.click()')
        time.sleep(0.3)
        val('document.querySelector(\'table input[type=checkbox][aria-label^="Select "]\')?.click()')
        time.sleep(0.3)
        val("[...document.querySelectorAll('button')].find(b=>b.textContent?.includes('Actions for'))?.click()")
        time.sleep(0.4)
        shot("library-actions-menu.png")
        val('document.querySelector(\'table button.font-semibold.text-cloudera-navy\')?.click()')
        time.sleep(3)
        results["Popup layering"] = "PASS" if val('!!document.querySelector(\'[role=menu]\')') is not True else "FAIL"
        detail_cb = val('!!document.querySelector(\'[data-testid="library-document-table-panel"] input[type=checkbox]\')')
        results["Detail default checkbox hidden"] = "PASS" if detail_cb is not True else "FAIL"
        shot("detail-default.png")
        val('document.querySelector(\'[aria-label="Select documents"]\')?.click()')
        time.sleep(0.5)
        shot("detail-selection-mode.png")
        val("[...document.querySelectorAll('button')].find(b=>/Actions for/.test(b.getAttribute('aria-label')||''))?.click()")
        time.sleep(0.4)
        shot("document-actions-menu.png")
        ws.close()
        overall = "PASS" if all(v == "PASS" for v in results.values()) else "FAIL"
        out = {"results": results, "overall": overall, "FE_KNOWLEDGE_V2_1_POLISH_PASS": overall}
        (EVID / "browser-evidence.json").write_text(json.dumps(out, indent=2))
        print(json.dumps(out, indent=2))
        return 0 if overall == "PASS" else 1
    finally:
        proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
