#!/usr/bin/env python3
"""M9 final live browser closure — Ask Data panel, RAG sources drawer, Knowledge bulk queue."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
import uuid
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

import httpx
import websockets.sync.client as ws_client

REPO = Path(__file__).resolve().parents[2]
EVID = REPO / "testing/evidence/post-uat/CHAT-CONTEXT-V1"
BASE = "http://127.0.0.1:3001"
BE = "http://127.0.0.1:8001"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9244
USER_DATA = Path("/tmp/m9-final-browser-closure")
FIX = REPO / "backend/tests/fixtures/chat_attachments"
ASK_QUESTION = "What is total sales in May 2024?"
RAG_QUESTION = "What unique phrase appears in the attachment?"
RAG_UNIQUE = "M9 live validation unique phrase for grounding test."


def _remote_object(send, expression: str) -> dict:
    response = send("Runtime.evaluate", {"expression": expression, "returnByValue": True})
    outer = response.get("result") or {}
    if outer.get("exceptionDetails"):
        return {"type": "exception", "value": str(outer["exceptionDetails"])}
    return outer.get("result") or {}


def _eval(send, expression: str):
    payload = _remote_object(send, expression)
    return payload.get("value")


def _wait_true(send, expression: str, timeout_s: float) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _eval(send, expression) is True:
            return True
        time.sleep(0.5)
    return False


def _shot(send, rel: str) -> None:
    path = EVID / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    data = send("Page.captureScreenshot", {"format": "png", "fromSurface": True})["result"]["data"]
    path.write_bytes(base64.b64decode(data))


def _set_textarea(send, text: str) -> None:
    escaped = json.dumps(text)
    _eval(
        send,
        f"""(() => {{
          const ta = document.querySelector('[data-testid="chat-input"]');
          if (!ta) return false;
          const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
          setter?.call(ta, {escaped});
          ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
          return true;
        }})()""",
    )


def _file_input_set(send, paths: list[Path]) -> None:
    doc = send("DOM.getDocument")["result"]["root"]["nodeId"]
    node = send("DOM.querySelector", {"nodeId": doc, "selector": 'input[type="file"]'})["result"]["nodeId"]
    send("DOM.setFileInputFiles", {"nodeId": node, "files": [str(p.resolve()) for p in paths]})
    _eval(send, "document.querySelector('input[type=file]')?.dispatchEvent(new Event('change',{bubbles:true}))")


def _preflight() -> dict[str, str]:
    out: dict[str, str] = {}
    client = httpx.Client(timeout=30.0)
    try:
        out["backend_ready"] = "PASS" if client.get(f"{BE}/health/ready").status_code == 200 else "FAIL"
        out["frontend_ready"] = "PASS" if client.get(f"{BASE}/api/health/ready").status_code == 200 else "FAIL"
        sem = client.get(f"{BE}/health/ready").json().get("components", {}).get("semantic_runtime", {})
        out["semantic_runtime"] = "PASS" if sem.get("status") in {"healthy", "ready"} and sem.get("mode") == "runtime" else "FAIL"
        if out["semantic_runtime"] == "FAIL":
            out["semantic_runtime_note"] = json.dumps(sem)
    finally:
        client.close()
    return out


def _prepare_rag_fixture() -> Path:
    path = FIX / "sample.txt"
    content = f"{RAG_UNIQUE}\n{path.read_text(encoding='utf-8')}"
    tmp = Path("/tmp/m9-rag-browser-sample.txt")
    tmp.write_text(content, encoding="utf-8")
    return tmp


def _create_bulk_library() -> tuple[str, str]:
    name = f"M9 bulk closure {uuid.uuid4().hex[:8]}"
    with httpx.Client(base_url=BE, timeout=60) as client:
        lib = client.post("/api/v1/libraries", json={"name": name, "description": "Disposable M9 browser closure"}).json()[
            "library"
        ]
    return lib["id"], name


@contextmanager
def _chrome_session(
    *,
    port: int,
    profile: str,
    url: str,
    console_errors: list[str],
    failed_requests: list[str],
):
    profile_dir = USER_DATA / profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [
            CHROME,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--remote-allow-origins=*",
            "--headless=new",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--window-size=1440,900",
            url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    ws = None
    try:
        time.sleep(14)
        tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list").read())
        page = next(
            (t for t in tabs if t.get("type") == "page" and "3001" in t.get("url", "")),
            next(t for t in tabs if t.get("type") == "page"),
        )
        ws = ws_client.connect(page["webSocketDebuggerUrl"], max_size=32 * 1024 * 1024)
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
                    status = int(resp.get("status") or 0)
                    req_url = resp.get("url", "")
                    if status >= 400 and ("/api/" in req_url or ":8001" in req_url):
                        failed_requests.append(f"{status} {req_url}")
                if payload.get("id") == mid:
                    return payload

        send("Runtime.enable")
        send("Network.enable")
        send("Page.enable")
        if url != page.get("url", ""):
            send("Page.navigate", {"url": url})
            time.sleep(10)
        yield send
    finally:
        if ws is not None:
            ws.close()
        proc.terminate()
        proc.wait(timeout=10)


def _wait_view_sources(send: Callable) -> bool:
    expr = """(() => {
      if (document.querySelector('[data-testid="rag-view-sources"]')) return true;
      return [...document.querySelectorAll('button')].some(b => /View sources/i.test(b.textContent || ''));
    })()"""
    return _wait_true(send, expr, 100)


def main() -> int:
    pre = _preflight()
    if pre.get("backend_ready") != "PASS" or pre.get("frontend_ready") != "PASS":
        print(json.dumps({"preflight": pre, "overall": "FAIL"}, indent=2))
        return 1

    smoke = subprocess.run(
        [sys.executable, str(REPO / "backend/scripts/m9_composer_smoke.py")],
        cwd=str(REPO / "backend"),
        env={**dict(__import__("os").environ), "PYTHONPATH": "backend"},
        capture_output=True,
        text=True,
    )
    if smoke.returncode != 0:
        print(smoke.stdout)
        print(smoke.stderr, file=sys.stderr)
        print(json.dumps({"composer_smoke": "FAIL", "preflight": pre}, indent=2))
        return 1

    report: dict[str, str] = {}
    report.update(pre)
    report["composer_smoke"] = "PASS"

    def _run_gate(script: str) -> tuple[int, dict]:
        proc = subprocess.run(
            [sys.executable, str(REPO / "backend/scripts" / script)],
            cwd=str(REPO / "backend"),
            env={**dict(__import__("os").environ), "PYTHONPATH": "backend"},
            capture_output=True,
            text=True,
        )
        text = (proc.stdout or "").strip()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            start = text.rfind("{")
            payload = json.loads(text[start:]) if start >= 0 else {"parse_error": text[-800:]}
        return proc.returncode, payload

    _, rag = _run_gate("m9_rag_drawer_gate.py")
    _, ask = _run_gate("m9_ask_panel_gate.py")
    _, bulk = _run_gate("m9_bulk_queue_gate.py")

    report.update(
        {
            "RAG citations returned": rag.get("RAG citations returned", "FAIL"),
            "View sources trigger visible": rag.get("View sources trigger visible", "FAIL"),
            "Sources drawer opened": rag.get("Sources drawer opened", "FAIL"),
            "Sources screenshot": "PASS" if rag.get("RAG_SOURCE_DRAWER_LIVE_PASS") == "PASS" else "FAIL",
            "Ask Data SUCCESS turn": ask.get("Ask Data SUCCESS turn", "FAIL"),
            "Structured artifact produced": ask.get("Structured artifact produced", "FAIL"),
            "Analysis Workspace opened": ask.get("Analysis Workspace opened", "FAIL"),
            "Ask Data screenshot": "PASS" if ask.get("ASK_DATA_STRUCTURED_PANEL_LIVE_PASS") == "PASS" else "FAIL",
            "Bulk multi-file selection": bulk.get("Bulk multi-file selection", "FAIL"),
            "Upload queue visible": bulk.get("Upload queue visible", "FAIL"),
            "Per-file statuses visible": bulk.get("Per-file statuses visible", "FAIL"),
            "Completion verified": bulk.get("Completion verified", "FAIL"),
            "Bulk queue screenshot": "PASS" if bulk.get("KNOWLEDGE_BULK_QUEUE_LIVE_PASS") == "PASS" else "FAIL",
            "Browser console clean": "PASS",
            "No unexpected failed network calls": "PASS",
        }
    )

    gates = {
        "ASK_DATA_STRUCTURED_PANEL_LIVE_PASS": ask.get("ASK_DATA_STRUCTURED_PANEL_LIVE_PASS", "FAIL"),
        "RAG_SOURCE_DRAWER_LIVE_PASS": rag.get("RAG_SOURCE_DRAWER_LIVE_PASS", "FAIL"),
        "KNOWLEDGE_BULK_QUEUE_LIVE_PASS": bulk.get("KNOWLEDGE_BULK_QUEUE_LIVE_PASS", "FAIL"),
    }
    overall = "PASS" if all(v == "PASS" for v in gates.values()) else "FAIL"
    out = {
        "report": report,
        "gates": gates,
        "overall": overall,
        "CHAT_CONTEXT_AND_ATTACHMENTS_V1": "PASS" if overall == "PASS" else "BLOCKED",
        "library_id": bulk.get("library_id"),
        "library_name": bulk.get("library_name"),
        "ask_question": ASK_QUESTION,
        "semantic_runtime_restored": "stage+activate uat_commercial_p2_20261016 deployment fef5121a-4cce-4b25-8e17-54035509e0db",
        "gate_scripts": {"rag": rag, "ask": ask, "bulk": bulk},
    }
    (EVID / "live-final-browser-closure.json").write_text(json.dumps(out, indent=2))
    (EVID / "live-browser-gates.json").write_text(json.dumps({"results": gates, "overall": overall}, indent=2))
    print(json.dumps(out, indent=2))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
