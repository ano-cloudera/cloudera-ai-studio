#!/usr/bin/env python3
"""Live browser gate: governed Ask Data + Analysis Workspace panel."""

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
EVID = REPO / "testing/evidence/post-uat/CHAT-CONTEXT-V1"
BASE = "http://127.0.0.1:3001"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
QUESTION = "What is total sales in May 2024?"


def main() -> int:
    proc = subprocess.Popen(
        [
            CHROME,
            "--remote-debugging-port=9259",
            "--user-data-dir=/tmp/m9-ask-panel-gate",
            "--remote-allow-origins=*",
            "--headless=new",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            BASE,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(12)
        tabs = json.loads(urllib.request.urlopen("http://127.0.0.1:9259/json/list").read())
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
        for _ in range(80):
            if val('!!document.querySelector(\'[data-testid="chat-composer"]\')') is True:
                break
            time.sleep(0.5)
        for _ in range(60):
            if val('document.querySelector(\'[data-testid="chat-send-button"]\')?.disabled') is not True:
                break
            time.sleep(0.5)
        val(
            f"""(() => {{
              const ta = document.querySelector('[data-testid="chat-input"]');
              const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
              setter?.call(ta, {json.dumps(QUESTION)});
              ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
              return true;
            }})()"""
        )
        val('document.querySelector(\'[data-testid="chat-send-button"]\')?.click()')
        ask_done = False
        for _ in range(360):
            body = val("document.body.innerText") or ""
            if "1,315.25" in body or "1315.25" in body:
                ask_done = True
                break
            time.sleep(0.5)
        panel = val('!!document.querySelector(\'[data-testid="analysis-workspace-panel"]\')') is True
        artifact = val(
            """(() => {
              const panel = document.querySelector('[data-testid="analysis-workspace-panel"]');
              if (!panel) return false;
              const t = panel.innerText || '';
              return t.includes('1,315') || t.includes('1315') || t.includes('Sales');
            })()"""
        )
        shot = EVID / "ANALYSIS-WORKSPACE" / "final-ask-data-panel.png"
        data = send("Page.captureScreenshot", {"format": "png"})["result"]["data"]
        shot.parent.mkdir(parents=True, exist_ok=True)
        shot.write_bytes(base64.b64decode(data))
        out = {
            "Ask Data SUCCESS turn": "PASS" if ask_done else "FAIL",
            "Structured artifact produced": "PASS" if artifact else "FAIL",
            "Analysis Workspace opened": "PASS" if panel else "FAIL",
            "ASK_DATA_STRUCTURED_PANEL_LIVE_PASS": "PASS"
            if ask_done and artifact and panel
            else "FAIL",
        }
        ws.close()
        print(json.dumps(out, indent=2))
        return 0 if out["ASK_DATA_STRUCTURED_PANEL_LIVE_PASS"] == "PASS" else 1
    finally:
        proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
