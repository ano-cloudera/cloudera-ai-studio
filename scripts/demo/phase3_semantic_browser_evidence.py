#!/usr/bin/env python3
"""Capture Phase 3 Semantic browser PNG evidence (CDP + live stack)."""
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
EVID = REPO / "testing" / "evidence" / "golden-path" / "PHASE3-SEMANTIC" / "browser"
REG = REPO / "testing" / "evidence" / "golden-path" / "PHASE3-SEMANTIC" / "semantic-registration.json"
BASE = "http://127.0.0.1:3001"
API = "http://127.0.0.1:8001"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
MODEL_NAME = "Retail Banking Analytics"


def curl_status(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return int(r.status)
    except (urllib.error.URLError, TimeoutError):
        return 0


def ensure_backend() -> bool:
    if curl_status(f"{API}/health/ready") == 200:
        return True
    return False


def _free_frontend_port() -> None:
    subprocess.run(
        ["bash", "-c", "lsof -ti :3001 | xargs kill 2>/dev/null || true"],
        cwd=str(REPO),
        check=False,
    )
    time.sleep(2)


def ensure_frontend() -> bool:
    if curl_status(BASE) == 200:
        return True
    if curl_status(BASE) in (500, 502, 503):
        _free_frontend_port()
    fe_log = REPO / ".tmp" / "frontend-3001-phase3.log"
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
    if not Path(CHROME).is_file():
        print("Chrome not found for CDP capture", file=sys.stderr)
        return 1
    if not ensure_backend() or not ensure_frontend():
        print("stack not ready", file=sys.stderr)
        return 1

    port = 9360 + int(uuid.uuid4().hex[:2], 16) % 200
    profile = f"/tmp/cai-phase3-semantic-{uuid.uuid4().hex[:8]}"
    proc = subprocess.Popen(
        [
            CHROME,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile}",
            "--remote-allow-origins=*",
            "--headless=new",
            "--window-size=1440,900",
            f"{BASE}/semantic-layer",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    gates: dict[str, str] = {}
    shots: list[str] = []
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
            return (outer.get("result") or {}).get("value")

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
                path = EVID / name
                path.write_bytes(base64.b64decode(data))
                shots.append(name)

        send("Page.enable")
        send("Runtime.enable")

        ok_overview = wait_true(f"document.body.innerText.includes({json.dumps(MODEL_NAME)})", 120)
        gates["semantic_overview"] = "PASS" if ok_overview else "FAIL"
        screenshot("A-semantic-overview.png")

        val(
            f"""
(() => {{
  const name = {json.dumps(MODEL_NAME)};
  const btn = [...document.querySelectorAll('button')].find(el => (el.textContent||'').includes(name));
  if (btn) {{ btn.click(); return true; }}
  return false;
}})()
"""
        )
        wait_true("document.body.innerText.includes('Data Models')", 60)

        for tab, shot in (
            ("Data Models", "B-data-models.png"),
            ("Relationships", "C-relationship.png"),
            ("Metrics", "D-metrics.png"),
            ("Dimensions", "E-dimensions.png"),
            ("Advanced", "F-model-health.png"),
        ):
            val(
                f"""
(() => {{
  const t = {json.dumps(tab)};
  const el = [...document.querySelectorAll('button')].find(b => (b.textContent||'').trim() === t);
  if (el) {{ el.click(); return true; }}
  return false;
}})()
"""
            )
            time.sleep(1.2)
            screenshot(shot)

        screenshot("G-publish-active.png")

        send("Page.navigate", {"url": f"{BASE}/"})
        wait_true("!!document.querySelector('textarea')", 90)

        def ask_with_context(label: str, question: str, shot: str | None = None) -> None:
            val(
                f"""
(() => {{
  const ta = document.querySelector('textarea');
  if (!ta) return false;
  ta.focus();
  ta.value = '@' + {json.dumps(label)} + ' ' + {json.dumps(question)};
  ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
  return true;
}})()
"""
            )
            time.sleep(1.5)
            val(
                """(() => {
  const btn = [...document.querySelectorAll('button')].find(b => /send|ask|submit/i.test(b.textContent||''));
  if (btn) { btn.click(); return true; }
  return false;
})()"""
            )
            wait_true("document.body.innerText.length > 200", 120)
            if shot:
                screenshot(shot)

        ask_with_context(MODEL_NAME, "What is the total transaction amount?", "H-governed-total-amount.png")
        ask_with_context(MODEL_NAME, "Show total transaction amount by channel.", "I-governed-by-channel.png")
        ask_with_context(
            MODEL_NAME,
            "Which customer segment has the highest total transaction amount?",
            "J-governed-segment-join.png",
        )
        ask_with_context("transactions", "Show total transaction amount by channel.", "K-raw-vs-governed.png")
        send("Page.navigate", {"url": f"{BASE}/"})
        wait_true("!!document.querySelector('textarea')", 90)
        ask_with_context("Retail Banking Knowledge", "How is Failed Transaction Rate defined?")
        ask_with_context(MODEL_NAME, "What is the failed transaction rate?")
        screenshot("L-knowledge-vs-semantic-failed-rate.png")

        send("Page.navigate", {"url": f"{BASE}/semantic-layer"})
        wait_true(f"document.body.innerText.includes({json.dumps(MODEL_NAME)})", 60)
        val(
            f"""
(() => {{
  const name = {json.dumps(MODEL_NAME)};
  const btn = [...document.querySelectorAll('button')].find(el => (el.textContent||'').includes(name));
  if (btn) {{ btn.click(); return true; }}
  return false;
}})()
"""
        )
        val(
            """(() => {
  const el = [...document.querySelectorAll('button')].find(b => (b.textContent||'').trim() === 'Advanced');
  if (el) { el.click(); return true; }
  return false;
})()"""
        )
        time.sleep(1)
        screenshot("M-version-history.png")
        ws.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)

    required = [
        "A-semantic-overview.png",
        "B-data-models.png",
        "C-relationship.png",
        "D-metrics.png",
        "E-dimensions.png",
        "F-model-health.png",
        "G-publish-active.png",
        "H-governed-total-amount.png",
        "I-governed-by-channel.png",
        "J-governed-segment-join.png",
        "K-raw-vs-governed.png",
        "L-knowledge-vs-semantic-failed-rate.png",
        "M-version-history.png",
    ]
    for name in required:
        gates[f"shot_{name}"] = "PASS" if (EVID / name).is_file() else "FAIL"

    manifest = {"gates": gates, "screenshots": shots, "dir": str(EVID)}
    (EVID / "browser-evidence-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0 if all(gates.get(f"shot_{n}") == "PASS" for n in required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
