#!/usr/bin/env python3
"""Capture Phase 2 Knowledge browser evidence (CDP + live stack)."""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import websockets.sync.client as ws_client

REPO = Path(__file__).resolve().parents[2]
EVID = REPO / "testing" / "evidence" / "golden-path" / "PHASE2-KNOWLEDGE"
REG = EVID / "library-registration.json"
BASE = "http://127.0.0.1:3001"
API = "http://127.0.0.1:8001"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BACKEND_SH = REPO / "scripts/dev-backend.sh"


def curl_status(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return int(r.status)
    except (urllib.error.URLError, TimeoutError):
        return 0


def ensure_backend() -> bool:
    if curl_status(f"{API}/health/ready") == 200:
        return True
    subprocess.run([str(BACKEND_SH), "start"], cwd=str(REPO), check=False)
    for _ in range(80):
        if curl_status(f"{API}/health/ready") == 200:
            return True
        time.sleep(0.5)
    return False


def ensure_frontend() -> bool:
    if curl_status(BASE) == 200:
        return True
    fe_log = REPO / ".tmp" / "frontend-3001-phase2.log"
    fe_log.parent.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        ["npm", "run", "dev", "--", "-p", "3001"],
        cwd=str(REPO / "frontend"),
        stdout=fe_log.open("w"),
        stderr=subprocess.STDOUT,
    )
    for _ in range(90):
        if curl_status(BASE) == 200:
            return True
        time.sleep(1)
    return False


def main() -> int:
    EVID.mkdir(parents=True, exist_ok=True)
    if not REG.is_file():
        print("missing library-registration.json — run register_banking_knowledge.py", file=sys.stderr)
        return 1
    reg = json.loads(REG.read_text(encoding="utf-8"))
    library_id = reg["library_id"]
    library_name = reg.get("library_name", "Retail Banking Knowledge")

    if not ensure_backend() or not ensure_frontend():
        print("stack not ready", file=sys.stderr)
        return 1

    port = 9260 + int(uuid.uuid4().hex[:2], 16) % 200
    profile = f"/tmp/cai-phase2-knowledge-{uuid.uuid4().hex[:8]}"
    proc = subprocess.Popen(
        [
            CHROME,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile}",
            "--remote-allow-origins=*",
            "--headless=new",
            "--window-size=1440,900",
            f"{BASE}/knowledge",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    gates: dict[str, str] = {}
    try:
        time.sleep(3)
        tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=8).read())
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
            outer = send(
                "Runtime.evaluate",
                {"expression": expression, "returnByValue": True, "awaitPromise": True},
            ).get("result") or {}
            inner = outer.get("result") or {}
            return inner.get("value")

        def wait_true(expr: str, timeout: float = 90.0) -> bool:
            deadline = time.time() + timeout
            while time.time() < deadline:
                if val(expr) is True:
                    return True
                time.sleep(0.4)
            return False

        def screenshot(name: str) -> None:
            data = ((send("Page.captureScreenshot", {"format": "png"}).get("result") or {}).get("data") or "")
            if data:
                (EVID / name).write_bytes(base64.b64decode(data))

        send("Page.enable")
        send("Runtime.enable")

        ok_land = wait_true(f"document.body.innerText.includes({json.dumps(library_name)})", 120)
        gates["knowledge_landing"] = "PASS" if ok_land else "FAIL"
        screenshot("A-knowledge-landing.png")

        clicked = val(
            f"""
(() => {{
  const name = {json.dumps(library_name)};
  const btn = [...document.querySelectorAll('button')].find(
    el => (el.textContent || '').trim() === name
  );
  if (btn) {{ btn.click(); return true; }}
  return false;
}})()
"""
        )
        gates["library_detail_open"] = "PASS" if clicked else "FAIL"
        wait_true(f"document.querySelector('h1')?.textContent?.includes({json.dumps(library_name)})", 60)
        ok_docs = wait_true(
            "document.body.innerText.includes('Transaction Policy') && "
            "document.body.innerText.includes('Segment and Risk Guide')",
            120,
        )
        gates["library_detail_two_documents"] = "PASS" if ok_docs else "FAIL"
        screenshot("B-library-detail-documents.png")

        send("Page.navigate", {"url": f"{BASE}/"})
        gates["ask_composer"] = "PASS" if wait_true("!!document.querySelector('textarea')", 90) else "FAIL"
        screenshot("G-ask-composer.png")
        ws.close()

    finally:
        proc.terminate()
        proc.wait(timeout=10)

    manifest = {
        "phase": "GOLDEN_PATH_BANKING_DEMO_PHASE2_KNOWLEDGE",
        "captured_at": time.strftime("%Y-%m-%d"),
        "library_id": library_id,
        "library_name": library_name,
        "artifacts": {
            "library_registration": str(REG.relative_to(REPO)),
            "api_rag_evidence": "testing/evidence/golden-path/PHASE2-KNOWLEDGE/api-rag-evidence.json",
            "documentation": "docs/demo/GOLDEN_BANKING_KNOWLEDGE.md",
            "screenshots": [
                "testing/evidence/golden-path/PHASE2-KNOWLEDGE/A-knowledge-landing.png",
                "testing/evidence/golden-path/PHASE2-KNOWLEDGE/B-library-detail-documents.png",
                "testing/evidence/golden-path/PHASE2-KNOWLEDGE/G-ask-composer.png",
            ],
        },
        "ui_checks": [
            {"area": "Knowledge landing", "route": "/knowledge", "expected": f"{library_name} listed"},
            {"area": "Library detail", "expected": "Both Golden Banking PDFs listed"},
            {"area": "Sources drawer", "note": "pytest RAG citation tests + api-rag-evidence retrieval"},
            {"area": "Raw vs Knowledge contrast", "note": "api-rag-evidence routing.contrast_ok"},
        ],
        "gates": gates,
    }
    (EVID / "browser-evidence-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    required = ("knowledge_landing", "library_detail_open", "library_detail_two_documents", "ask_composer")
    return 0 if all(gates.get(k) == "PASS" for k in required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
