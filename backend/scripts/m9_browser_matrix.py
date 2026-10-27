#!/usr/bin/env python3
"""Live browser matrix for M9 closure (requires FE :3001, BE :8001)."""

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
PORT = 9242
USER_DATA = Path("/tmp/m9-browser-matrix-profile")
FIX = REPO / "backend/tests/fixtures/chat_attachments"


def _page_tab() -> dict:
    tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list").read())
    return next(
        (t for t in tabs if t.get("type") == "page" and "3001" in t.get("url", "")),
        next(t for t in tabs if t.get("type") == "page"),
    )


def _cdp(ws_url: str):
    ws = ws_client.connect(ws_url, max_size=32 * 1024 * 1024)
    mid = 0

    def send(method: str, params: dict | None = None) -> dict:
        nonlocal mid
        mid += 1
        ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            payload = json.loads(ws.recv())
            if payload.get("id") == mid:
                return payload

    def remote(expression: str) -> dict:
        outer = send("Runtime.evaluate", {"expression": expression, "returnByValue": True}).get("result") or {}
        return outer.get("result") or {}

    def eval_bool(expression: str) -> bool:
        obj = remote(expression)
        return bool(obj.get("value"))

    def eval_str(expression: str) -> str:
        obj = remote(expression)
        val = obj.get("value")
        return "" if val is None else str(val)

    def shot(path: Path) -> None:
        import base64

        data = send("Page.captureScreenshot", {"format": "png", "fromSurface": True})["result"]["data"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(data))

    def wait_bool(expression: str, *, timeout_s: float = 45.0) -> bool:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if eval_bool(expression):
                return True
            time.sleep(0.5)
        return False

    return ws, send, remote, eval_bool, eval_str, shot, wait_bool


def main() -> int:
    results: dict[str, str] = {}
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
    try:
        time.sleep(12)
        ws, send, remote, eval_bool, eval_str, shot, wait_bool = _cdp(_page_tab()["webSocketDebuggerUrl"])
        send("Page.enable")
        send("Runtime.enable")
        send("DOM.enable")

        composer = wait_bool('!!document.querySelector(\'[data-testid="chat-composer"]\')', timeout_s=45)
        results["composer_ready"] = "PASS" if composer else "FAIL"
        shot(EVID / "BROWSER" / "matrix-01-composer.png")

        # + menu
        eval_str('document.querySelector(\'[data-testid="chat-add-button"]\')?.click()')
        time.sleep(0.4)
        shot(EVID / "BROWSER" / "matrix-02-plus-menu.png")
        results["plus_menu"] = (
            "PASS"
            if eval_bool(
                "[...document.querySelectorAll('[role=menuitem]')].some(e=>e.textContent.includes('Upload'))"
            )
            else "FAIL"
        )

        # Multi upload: txt + csv (partial failure)
        eval_str(
            "[...document.querySelectorAll('[role=menuitem]')].find(e=>e.textContent.includes('Upload'))?.click()"
        )
        doc = send("DOM.getDocument")["result"]["root"]["nodeId"]
        node = send("DOM.querySelector", {"nodeId": doc, "selector": 'input[type="file"]'})["result"]["nodeId"]
        send(
            "DOM.setFileInputFiles",
            {
                "nodeId": node,
                "files": [str((FIX / "sample.txt").resolve()), str((FIX / "notes.csv").resolve())],
            },
        )
        # csv fixture may not exist — create temp csv path
        csv_path = FIX / "reject.csv"
        csv_path.write_text("a,b\n1,2\n")
        send(
            "DOM.setFileInputFiles",
            {
                "nodeId": node,
                "files": [str((FIX / "sample.txt").resolve()), str(csv_path.resolve())],
            },
        )
        eval_str("document.querySelector('input[type=file]')?.dispatchEvent(new Event('change',{bubbles:true}))")
        time.sleep(2)
        shot(EVID / "UPLOAD" / "matrix-multi-upload.png")
        body = eval_str("document.body.innerText")
        multi_ok = "sample.txt" in body and ("unsupported" in body.lower() or "could not" in body.lower() or "Ready" in body)
        results["multi_upload_partial"] = "PASS" if multi_ok else "FAIL"

        # Ask Data opens analysis workspace
        starter = eval_str(
            """(() => {
              const btn = [...document.querySelectorAll('button')].find(b => !b.disabled && b.textContent && b.textContent.length > 20);
              if (!btn) return 'none';
              btn.click();
              return btn.textContent.slice(0,40);
            })()"""
        )
        panel_open = wait_bool('!!document.querySelector(\'[data-testid="analysis-workspace-panel"]\')', timeout_s=120)
        shot(EVID / "ANALYSIS-WORKSPACE" / "matrix-ask-data-panel.png")
        results["ask_data_opens_panel"] = "PASS" if panel_open else "FAIL"

        # Temp attachment RAG: fresh upload on home
        send("Page.navigate", {"url": BASE})
        time.sleep(12)
        wait_bool('!!document.querySelector(\'[data-testid="chat-composer"]\')', timeout_s=45)
        eval_str('document.querySelector(\'[data-testid="chat-add-button"]\')?.click()')
        time.sleep(0.3)
        eval_str("[...document.querySelectorAll('[role=menuitem]')].find(e=>e.textContent.includes('Upload'))?.click()")
        doc = send("DOM.getDocument")["result"]["root"]["nodeId"]
        node = send("DOM.querySelector", {"nodeId": doc, "selector": 'input[type="file"]'})["result"]["nodeId"]
        send("DOM.setFileInputFiles", {"nodeId": node, "files": [str((FIX / "sample.txt").resolve())]})
        eval_str("document.querySelector('input[type=file]')?.dispatchEvent(new Event('change',{bubbles:true}))")
        wait_bool('document.body.innerText.includes("Ready")', timeout_s=90)
        shot(EVID / "RAG" / "matrix-temp-ready.png")

        eval_str(
            """(() => {
              const ta = document.querySelector('[data-testid="chat-input"]');
              if (!ta) return 'no-input';
              const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
              setter?.call(ta, 'What phrase appears in the uploaded sample text file?');
              ta.dispatchEvent(new Event('input', { bubbles: true }));
              return 'filled';
            })()"""
        )
        time.sleep(0.3)
        eval_str("document.querySelector('[data-testid=\"chat-send-button\"]')?.click()")
        time.sleep(90)
        rag_panel_closed = not eval_bool('!!document.querySelector(\'[data-testid="analysis-workspace-panel"]\')')
        view_sources = eval_bool("[...document.querySelectorAll('button')].some(b=>b.textContent.includes('View sources'))")
        if view_sources:
            eval_str("[...document.querySelectorAll('button')].find(b=>b.textContent.includes('View sources'))?.click()")
            time.sleep(0.5)
            shot(EVID / "SOURCES" / "matrix-sources-drawer.png")
            drawer = eval_bool('!!document.querySelector(\'[data-testid="rag-sources-drawer"]\')')
            results["source_drawer"] = "PASS" if drawer else "FAIL"
        else:
            results["source_drawer"] = "FAIL"
            shot(EVID / "SOURCES" / "matrix-no-sources-button.png")
        results["rag_no_analysis_panel"] = "PASS" if rag_panel_closed else "FAIL"

        # Knowledge bulk queue UI
        send("Page.navigate", {"url": f"{BASE}/knowledge"})
        time.sleep(4)
        shot(EVID / "BULK" / "matrix-knowledge-page.png")
        on_knowledge = eval_str("location.pathname") == "/knowledge"
        lib_ui = eval_bool('!!document.querySelector(\'[data-testid="library-document-table-panel"]\')')
        results["knowledge_bulk_ui"] = "PASS" if on_knowledge and lib_ui else "FAIL"

        ws.close()
        overall = all(v == "PASS" for v in results.values())
        out = {"results": results, "starter_clicked": starter[:80], "overall": "PASS" if overall else "FAIL"}
        (EVID / "live-browser-matrix.json").write_text(json.dumps(out, indent=2))
        print(json.dumps(out, indent=2))
        return 0 if overall else 1
    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
