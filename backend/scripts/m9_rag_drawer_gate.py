#!/usr/bin/env python3
"""Live browser gate: temp attachment RAG + sources drawer only."""

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
FIX = REPO / "backend/tests/fixtures/chat_attachments/sample.txt"
QUESTION = "What unique phrase appears in the attachment?"
TOKEN = "M9 live validation unique phrase for grounding test."


def main() -> int:
    tmp = Path("/tmp/m9-rag-gate.txt")
    tmp.write_text(f"{TOKEN}\n{FIX.read_text(encoding='utf-8')}", encoding="utf-8")
    proc = subprocess.Popen(
        [
            CHROME,
            "--remote-debugging-port=9258",
            "--user-data-dir=/tmp/m9-rag-drawer-gate",
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
        tabs = json.loads(urllib.request.urlopen("http://127.0.0.1:9258/json/list").read())
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
        val('document.querySelector(\'[data-testid="chat-add-button"]\')?.click()')
        time.sleep(0.3)
        val("[...document.querySelectorAll('[role=menuitem]')].find(e=>/Upload files/i.test(e.textContent||''))?.click()")
        doc = send("DOM.getDocument")["result"]["root"]["nodeId"]
        node = send("DOM.querySelector", {"nodeId": doc, "selector": 'input[type="file"]'})["result"]["nodeId"]
        send("DOM.setFileInputFiles", {"nodeId": node, "files": [str(tmp.resolve())]})
        val("document.querySelector('input[type=file]')?.dispatchEvent(new Event('change',{bubbles:true}))")
        ready = False
        for _ in range(120):
            body = val("document.body.innerText") or ""
            if "Ready" in body and ".txt" in body:
                ready = True
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
        view_sources = False
        for _ in range(200):
            view_sources = val(
                """(() => {
                  return !!document.querySelector('[data-testid="rag-view-sources"]')
                    || [...document.querySelectorAll('button')].some(b => /View sources/i.test(b.textContent || ''));
                })()"""
            )
            if view_sources is True:
                break
            time.sleep(0.5)
        if view_sources:
            val(
                """(() => {
                  const btn = document.querySelector('[data-testid="rag-view-sources"]')
                    || [...document.querySelectorAll('button')].find(b => /View sources/i.test(b.textContent || ''));
                  btn?.click();
                  return !!btn;
                })()"""
            )
            time.sleep(0.5)
        drawer = val('!!document.querySelector(\'[data-testid="rag-sources-drawer"]\')') is True
        items = int(val('document.querySelectorAll(\'[data-testid="rag-source-item"], [data-testid="rag-sources-drawer"] li\').length') or 0)
        text = str(val('document.querySelector(\'[data-testid="rag-sources-drawer"]\')?.innerText ?? ""'))
        bad = "document_storage" in text or "s3://" in text
        shot = EVID / "SOURCES" / "final-sources-drawer.png"
        data = send("Page.captureScreenshot", {"format": "png"})["result"]["data"]
        shot.parent.mkdir(parents=True, exist_ok=True)
        shot.write_bytes(base64.b64decode(data))
        snippet = (val("document.body.innerText") or "")[:1200]
        out = {
            "attachment_ready": "PASS" if ready else "FAIL",
            "body_snippet": snippet,
            "RAG citations returned": "PASS" if view_sources else "FAIL",
            "View sources trigger visible": "PASS" if view_sources else "FAIL",
            "Sources drawer opened": "PASS" if drawer and items >= 1 and not bad else "FAIL",
            "RAG_SOURCE_DRAWER_LIVE_PASS": "PASS"
            if view_sources and drawer and items >= 1 and not bad
            else "FAIL",
        }
        ws.close()
        print(json.dumps(out, indent=2))
        return 0 if out["RAG_SOURCE_DRAWER_LIVE_PASS"] == "PASS" else 1
    finally:
        proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
