#!/usr/bin/env python3
"""Remaining live browser gates (composer must already be healthy)."""

from __future__ import annotations

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
PORT = 9243
FIX = REPO / "backend/tests/fixtures/chat_attachments"


def main() -> int:
    proc = subprocess.Popen(
        [
            CHROME,
            f"--remote-debugging-port={PORT}",
            "--user-data-dir=/tmp/m9-browser-gates",
            "--remote-allow-origins=*",
            "--headless=new",
            "--window-size=1440,900",
            BASE,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    results: dict[str, str] = {}
    try:
        time.sleep(12)
        tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list").read())
        page = next(t for t in tabs if t.get("type") == "page")
        ws = ws_client.connect(page["webSocketDebuggerUrl"], max_size=32 * 1024 * 1024)
        mid = 0

        def send(method: str, params: dict | None = None) -> dict:
            nonlocal mid
            mid += 1
            ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            while True:
                payload = json.loads(ws.recv())
                if payload.get("id") == mid:
                    return payload

        def val(expression: str):
            outer = send("Runtime.evaluate", {"expression": expression, "returnByValue": True}).get("result") or {}
            return (outer.get("result") or {}).get("value")

        def wait_true(expr: str, timeout: float) -> bool:
            deadline = time.time() + timeout
            while time.time() < deadline:
                if val(expr) is True:
                    return True
                time.sleep(0.5)
            return False

        def shot(name: str) -> None:
            import base64

            p = EVID / name
            p.parent.mkdir(parents=True, exist_ok=True)
            data = send("Page.captureScreenshot", {"format": "png", "fromSurface": True})["result"]["data"]
            p.write_bytes(base64.b64decode(data))

        if not wait_true('!!document.querySelector(\'[data-testid="chat-composer"]\')', 45):
            print(json.dumps({"error": "composer_not_ready"}, indent=2))
            return 1

        # Ask Data opens analysis workspace
        val(
            "(() => { const b=[...document.querySelectorAll('button')].find(x=>!x.disabled && x.textContent?.length>20); b?.click(); return true; })()"
        )
        ask_panel = wait_true('!!document.querySelector(\'[data-testid="analysis-workspace-panel"]\')', 120)
        results["ask_data_opens_panel"] = "PASS" if ask_panel else "FAIL"
        shot("ANALYSIS-WORKSPACE/matrix-ask-data-panel.png")

        # Temp attachment + RAG sources drawer
        send("Page.navigate", {"url": BASE})
        time.sleep(10)
        wait_true('!!document.querySelector(\'[data-testid="chat-composer"]\')', 45)
        val('document.querySelector(\'[data-testid="chat-add-button"]\')?.click()')
        time.sleep(0.3)
        val("[...document.querySelectorAll('[role=menuitem]')].find(e=>e.textContent.includes('Upload'))?.click()")
        doc = send("DOM.getDocument")["result"]["root"]["nodeId"]
        node = send("DOM.querySelector", {"nodeId": doc, "selector": 'input[type="file"]'})["result"]["nodeId"]
        send("DOM.setFileInputFiles", {"nodeId": node, "files": [str((FIX / "sample.txt").resolve())]})
        val("document.querySelector('input[type=file]')?.dispatchEvent(new Event('change',{bubbles:true}))")
        wait_true('document.body.innerText.includes("Ready")', 90)
        val(
            """(() => {
              const ta = document.querySelector('[data-testid="chat-input"]');
              const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
              setter?.call(ta, 'What does the sample text file say?');
              ta.dispatchEvent(new Event('input', { bubbles: true }));
              return true;
            })()"""
        )
        val('document.querySelector(\'[data-testid="chat-send-button"]\')?.click()')
        has_sources = wait_true("[...document.querySelectorAll('button')].some(b=>b.textContent.includes('View sources'))", 120)
        if has_sources:
            val("[...document.querySelectorAll('button')].find(b=>b.textContent.includes('View sources'))?.click()")
            time.sleep(0.5)
            drawer = val('!!document.querySelector(\'[data-testid="rag-sources-drawer"]\')') is True
            results["source_drawer"] = "PASS" if drawer else "FAIL"
            shot("SOURCES/matrix-sources-drawer.png")
        else:
            results["source_drawer"] = "FAIL"
        results["rag_no_analysis_panel"] = "PASS" if val('!!document.querySelector(\'[data-testid="analysis-workspace-panel"]\')') is not True else "FAIL"

        send("Page.navigate", {"url": f"{BASE}/knowledge"})
        time.sleep(4)
        val(
            """(() => {
              const row = document.querySelector('[data-testid="library-document-table-panel"]')
                || document.querySelector('a[href^="/knowledge"]')
                || [...document.querySelectorAll('button,a')].find(el => el.textContent?.trim() && el.textContent.length < 80);
              row?.click?.();
              return true;
            })()"""
        )
        time.sleep(2)
        val("(() => { const link=[...document.querySelectorAll('a,button')].find(e=>e.textContent?.includes('Upload documents')); link?.click(); return true; })()")
        results["knowledge_bulk_ui"] = (
            "PASS"
            if val("location.pathname") == "/knowledge"
            and (
                val('!!document.querySelector(\'[data-testid="library-document-table-panel"]\')') is True
                or val('!!document.querySelector(\'[data-testid="document-upload-queue"]\')') is True
                or val("document.body.innerText.includes('Upload documents')") is True
            )
            else "FAIL"
        )
        shot("BULK/matrix-knowledge-page.png")

        ws.close()
        out = {"results": results, "overall": "PASS" if all(v == "PASS" for v in results.values()) else "FAIL"}
        (EVID / "live-browser-gates.json").write_text(json.dumps(out, indent=2))
        print(json.dumps(out, indent=2))
        return 0 if out["overall"] == "PASS" else 1
    finally:
        proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
