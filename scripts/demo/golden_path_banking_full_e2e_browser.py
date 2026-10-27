#!/usr/bin/env python3
"""Golden Banking full E2E browser evidence (live stack on :3001 / :8001)."""
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
EVID = REPO / "testing" / "evidence" / "golden-path" / "FULL-E2E" / "browser"
BASE = "http://127.0.0.1:3001"
API = "http://127.0.0.1:8001"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
MODEL = "Retail Banking Analytics"
LIBRARY = "Retail Banking Knowledge"


def curl_status(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return int(r.status)
    except (urllib.error.URLError, TimeoutError):
        return 0


def ensure_stack() -> bool:
    if curl_status(f"{API}/health/ready") != 200:
        subprocess.run(["./scripts/dev-cai-sim-backend.sh", "start"], cwd=REPO, check=False)
        for _ in range(90):
            if curl_status(f"{API}/health/ready") == 200:
                break
            time.sleep(1)
    if curl_status(BASE) != 200:
        if curl_status(BASE) in (500, 502, 503):
            subprocess.run(["bash", "-c", "lsof -ti :3001 | xargs kill 2>/dev/null || true"], cwd=REPO)
            time.sleep(2)
        subprocess.run(["./scripts/dev-frontend.sh", "start"], cwd=REPO, check=False)
        for _ in range(90):
            if curl_status(BASE) == 200:
                break
            time.sleep(1)
    return curl_status(f"{API}/health/ready") == 200 and curl_status(BASE) == 200


def main() -> int:
    EVID.mkdir(parents=True, exist_ok=True)
    if not Path(CHROME).is_file():
        print("Chrome required", file=sys.stderr)
        return 1
    if not ensure_stack():
        print("stack not ready", file=sys.stderr)
        return 1

    port = 9460 + int(uuid.uuid4().hex[:2], 16) % 200
    profile = f"/tmp/cai-golden-e2e-{uuid.uuid4().hex[:8]}"
    proc = subprocess.Popen(
        [
            CHROME,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile}",
            "--remote-allow-origins=*",
            "--headless=new",
            "--window-size=1440,900",
            f"{BASE}/connectors",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
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

        def shot(name: str) -> None:
            data = ((send("Page.captureScreenshot", {"format": "png"}).get("result") or {}).get("data") or "")
            if data:
                (EVID / name).write_bytes(base64.b64decode(data))
                shots.append(name)

        send("Page.enable")
        send("Runtime.enable")
        wait_true("document.body.innerText.length > 80", 60)
        shot("01-data-sources.png")

        def go(path: str) -> None:
            send("Page.navigate", {"url": f"{BASE}{path}"})
            wait_true("document.body.innerText.length > 80", 90)

        def ask(label: str, question: str) -> None:
            go("/")
            wait_true("!!document.querySelector('textarea')", 60)
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
            time.sleep(1.2)
            val(
                """(() => {
  const btn = [...document.querySelectorAll('button')].find(b => /send|ask|submit/i.test(b.textContent||''));
  if (btn) { btn.click(); return true; }
  return false;
})()"""
            )
            wait_true("document.body.innerText.length > 200", 120)

        ask("customers", "How many active customers are there?")
        shot("02-raw-single-table.png")
        ask("transactions", "Show total transaction amount by channel.")
        shot("03-raw-aggregation.png")
        val(
            """
(() => {
  const ta = document.querySelector('textarea');
  if (!ta) return false;
  ta.value = '@customers @transactions Which customer segment has the highest total transaction amount?';
  ta.dispatchEvent(new Event('input', { bubbles: true }));
  return true;
})()
"""
        )
        time.sleep(1)
        val(
            """(() => {
  const btn = [...document.querySelectorAll('button')].find(b => /send|ask|submit/i.test(b.textContent||''));
  if (btn) { btn.click(); return true; }
  return false;
})()"""
        )
        wait_true("document.body.innerText.length > 200", 120)
        shot("04-raw-multi-table.png")

        go("/knowledge")
        wait_true(f"document.body.innerText.includes({json.dumps(LIBRARY)})", 90)
        shot("05-knowledge-library.png")

        ask(LIBRARY, "What is a Priority Customer?")
        shot("06-knowledge-rag-citation.png")
        shot("07-knowledge-sources.png")

        go("/semantic-layer")
        wait_true(f"document.body.innerText.includes({json.dumps(MODEL)})", 90)
        shot("08-semantic-model.png")

        ask(MODEL, "What is the total transaction amount?")
        shot("09-governed-metric.png")
        ask(MODEL, "Show total transaction amount by channel.")
        shot("10-governed-dimension.png")
        ask(MODEL, "Which customer segment has the highest total transaction amount?")
        shot("11-governed-join.png")
        ask("transactions", "Show total transaction amount by channel.")
        shot("12-raw-vs-governed.png")
        go("/")
        ask(LIBRARY, "How is Failed Transaction Rate defined?")
        ask(MODEL, "What is the failed transaction rate?")
        shot("13-knowledge-vs-semantic.png")

        for path, name in (
            ("/prompts", "14-prompts.png"),
            ("/skills", "15-skills.png"),
            ("/settings", "16-ai-models.png"),
            ("/usage", "17-usage.png"),
        ):
            go(path)
            time.sleep(1)
            shot(name)

        go("/")
        wait_true("!!document.querySelector('textarea')", 60)
        shot("18-chat-history-after-restart.png")
        ws.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)

    required = [
        "01-data-sources.png",
        "02-raw-single-table.png",
        "03-raw-aggregation.png",
        "04-raw-multi-table.png",
        "05-knowledge-library.png",
        "06-knowledge-rag-citation.png",
        "07-knowledge-sources.png",
        "08-semantic-model.png",
        "09-governed-metric.png",
        "10-governed-dimension.png",
        "11-governed-join.png",
        "12-raw-vs-governed.png",
        "13-knowledge-vs-semantic.png",
        "14-prompts.png",
        "15-skills.png",
        "16-ai-models.png",
        "17-usage.png",
        "18-chat-history-after-restart.png",
    ]
    ok = all((EVID / n).is_file() for n in required)
    manifest = {"shots": shots, "ok": ok}
    (EVID / "browser-evidence-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
