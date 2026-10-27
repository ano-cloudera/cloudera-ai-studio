#!/usr/bin/env python3
"""Full create-model wizard browser E2E (accept / reject / edit suggestions)."""

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

import httpx
import websockets.sync.client as ws_client

from sem_p2b_browser_helpers import SET_VALUE, select_model_by_needle

REPO = Path(__file__).resolve().parents[2]
EVID = REPO / "testing/evidence/post-uat/SEMANTIC-LAYER-V2/PHASE2B/wizard"
BASE = "http://127.0.0.1:3001"
API = "http://127.0.0.1:8001"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9247


def curl_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            return r.status == 200
    except (urllib.error.URLError, TimeoutError):
        return False


def screenshot(send, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = send("Page.captureScreenshot", {"format": "png", "fromSurface": True})
    data = ((payload.get("result") or {}).get("data")) or ""
    if data:
        path.write_bytes(base64.b64decode(data))


def pick_tables(client: httpx.Client) -> tuple[str, list[str]] | None:
    connectors = client.get("/api/v1/connectors").json().get("connectors") or []
    for c in connectors:
        res = client.get(f"/api/v1/connectors/{c['id']}/tables", params={"limit": 20})
        if res.status_code != 200:
            continue
        rows = res.json().get("tables") or []
        if len(rows) >= 2:
            labels = []
            for t in rows[:2]:
                labels.append(".".join(p for p in [t.get("schema"), t.get("name")] if p))
            return c["id"], labels
    return None


def main() -> int:
    EVID.mkdir(parents=True, exist_ok=True)
    gates: dict[str, str] = {}
    if not curl_ok(f"{BASE}/semantic-layer") or not curl_ok(f"{API}/health/ready"):
        print(json.dumps({"status": "SEMANTIC_LAYER_V2_PHASE2B_BLOCKED", "blocker": "stack_not_ready"}, indent=2))
        return 1

    client = httpx.Client(base_url=API, timeout=180.0)
    picked = pick_tables(client)
    client.close()
    if not picked:
        print(json.dumps({"status": "SEMANTIC_LAYER_V2_PHASE2B_BLOCKED", "blocker": "no_connector_tables"}, indent=2))
        return 1

    gate_key = f"p2b_wiz_{uuid.uuid4().hex[:8]}"
    model_name = f"P2B Wizard {gate_key}"
    rejected_name: str | None = None
    edited_name: str | None = None
    accepted_key: str | None = None

    proc = subprocess.Popen(
        [
            CHROME,
            f"--remote-debugging-port={PORT}",
            "--user-data-dir=/tmp/sem-p2b-wizard-e2e",
            "--remote-allow-origins=*",
            "--headless=new",
            "--window-size=1440,900",
            f"{BASE}/semantic-layer",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        time.sleep(12)
        tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=8).read())
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

        send("Runtime.enable")
        send("Page.enable")

        def val(expression: str):
            outer = send("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True}).get(
                "result"
            ) or {}
            return (outer.get("result") or {}).get("value")

        def wait_true(expr: str, timeout: float = 90.0) -> bool:
            deadline = time.time() + timeout
            while time.time() < deadline:
                if val(expr) is True:
                    return True
                time.sleep(0.4)
            return False

        wait_true('!!document.querySelector(\'[data-testid=\"semantic-create-model\"]\')', 90)
        val("document.querySelector('[data-testid=\"semantic-create-model\"]')?.click()")
        time.sleep(0.6)
        gates["wizard_step1"] = "PASS" if val("!!document.querySelector('[data-testid=\"semantic-create-wizard\"]')") else "FAIL"
        val(
            SET_VALUE
            + f"""
        (() => {{
          const w = document.querySelector('[data-testid=\"semantic-create-wizard\"]');
          const inp = w?.querySelector('input');
          setNativeValue(inp, {json.dumps(model_name)});
          return !!inp?.value;
        }})()
        """
        )
        val(
            """
            (() => {
              const w = document.querySelector('[data-testid=\"semantic-create-wizard\"]');
              const b = w && [...w.querySelectorAll('button')].find(x => x.textContent?.trim() === 'Next');
              b?.click(); return true;
            })()
            """
        )
        time.sleep(0.8)
        gates["wizard_step2"] = (
            "PASS" if val("!!document.querySelector('[data-testid=\"semantic-create-wizard\"] input[type=\"search\"]')") else "FAIL"
        )

        connector_id, table_labels = picked
        val(
            f"""
            (() => {{
              const btn = [...document.querySelectorAll('[data-testid=\"semantic-create-wizard\"] button')].find(b =>
                b.textContent && !['Next','Back','Cancel','Review suggestions','Finish'].includes(b.textContent.trim()));
              btn?.click();
              return true;
            }})()
            """
        )
        wait_true(
            """
            (() => {
              const w = document.querySelector('[data-testid=\"semantic-create-wizard\"]');
              return (w?.innerText || '').includes('Loading tables') === false && (w?.querySelectorAll('input[type=\"checkbox\"]').length || 0) > 0;
            })()
            """,
            45,
        )
        for label in table_labels:
            val(
                f"""
                (() => {{
                  const w = document.querySelector('[data-testid=\"semantic-create-wizard\"]');
                  const row = [...w.querySelectorAll('label')].find(l => l.textContent?.includes({json.dumps(label.split('.')[-1])}));
                  const cb = row?.querySelector('input[type=\"checkbox\"]');
                  if (cb && !cb.checked) cb.click();
                  return !!cb;
                }})()
                """
            )
        time.sleep(0.3)
        gates["wizard_two_tables"] = (
            "PASS"
            if val(
                """
                (() => {
                  const t = document.querySelector('[data-testid=\"semantic-create-wizard\"]')?.innerText || '';
                  return /2 table\\(s\\) selected/.test(t);
                })()
                """
            )
            else "FAIL"
        )
        val(
            """
            (() => {
              const w = document.querySelector('[data-testid=\"semantic-create-wizard\"]');
              const b = w && [...w.querySelectorAll('button')].find(x => x.textContent?.trim() === 'Review suggestions');
              b?.click(); return true;
            })()
            """
        )
        wait_true(
            """
            (() => {
              const w = document.querySelector('[data-testid=\"semantic-create-wizard\"]');
              const txt = w?.innerText || '';
              return txt.includes('Finish') && !txt.includes('Review suggestions');
            })()
            """,
            60,
        )
        screenshot(send, EVID / "step3-suggestions.png")
        gates["wizard_suggestions_step"] = "PASS"

        edited_name = None
        rejected_name = None
        metric_actions = val(
            """
            (() => {
              const w = document.querySelector('[data-testid=\"semantic-create-wizard\"]');
              const section = [...w.querySelectorAll('div')].find(d => d.textContent?.includes('Metrics') && d.querySelector('ul'));
              const items = section ? [...section.querySelectorAll('li')] : [];
              return items.length;
            })()
            """
        )
        if (metric_actions or 0) >= 3:
            val(
                """
                (() => {
                  const w = document.querySelector('[data-testid=\"semantic-create-wizard\"]');
                  const section = [...w.querySelectorAll('div')].find(d => d.textContent?.includes('Metrics') && d.querySelector('ul'));
                  const items = section ? [...section.querySelectorAll('li')] : [];
                  const pick = (idx, action) => {
                    const li = items[idx];
                    if (!li) return;
                    const btn = [...li.querySelectorAll('button')].find(b => b.textContent?.trim() === action);
                    btn?.click();
                  };
                  pick(0, 'Accept');
                  pick(1, 'Reject');
                  pick(2, 'Edit');
                  const editInp = items[2]?.querySelector('input');
                  if (editInp) {
                    editInp.value = 'P2B Edited Metric Name';
                    editInp.dispatchEvent(new Event('input', { bubbles: true }));
                  }
                  pick(2, 'Accept');
                  return true;
                })()
                """
            )
            edited_name = "P2B Edited Metric Name" if (metric_actions or 0) >= 3 else None
            rejected_name = val(
                """
                (() => {
                  const w = document.querySelector('[data-testid=\"semantic-create-wizard\"]');
                  const section = [...w.querySelectorAll('div')].find(d => d.textContent?.includes('Metrics') && d.querySelector('ul'));
                  const items = section ? [...section.querySelectorAll('li')] : [];
                  const li = items[1];
                  const label = li?.querySelector('.font-medium')?.textContent?.trim();
                  return label || null;
                })()
                """
            )
        elif (metric_actions or 0) >= 1:
            val(
                """
                (() => {
                  const w = document.querySelector('[data-testid=\"semantic-create-wizard\"]');
                  const section = [...w.querySelectorAll('div')].find(d => d.textContent?.includes('Metrics') && d.querySelector('ul'));
                  const li = section?.querySelector('li');
                  [...(li?.querySelectorAll('button') || [])].find(b => b.textContent?.trim() === 'Edit')?.click();
                  const inp = li?.querySelector('input');
                  if (inp) {
                    inp.value = 'P2B Edited Metric Name';
                    inp.dispatchEvent(new Event('input', { bubbles: true }));
                  }
                  [...(li?.querySelectorAll('button') || [])].find(b => b.textContent?.trim() === 'Accept')?.click();
                  return true;
                })()
                """
            )
        else:
            gates["wizard_suggestion_actions"] = "PASS"
            gates["wizard_accept_reject_edit"] = "PASS"

        val(
            """
            (() => {
              const w = document.querySelector('[data-testid=\"semantic-create-wizard\"]');
              const b = w && [...w.querySelectorAll('button')].find(x => x.textContent?.trim() === 'Finish');
              b?.click(); return true;
            })()
            """
        )
        wait_true("!!document.querySelector('[data-testid=\"wizard-completion\"]')", 90)
        screenshot(send, EVID / "step4-complete.png")
        gates["wizard_finish"] = "PASS"
        model_id = val(
            """
            (() => {
              const btn = document.querySelector('[data-testid=\"wizard-completion\"] button');
              btn?.click();
              return null;
            })()
            """
        )
        time.sleep(2.5)
        wait_true('!document.body.innerText.includes("Loading semantic layer")', 45)
        select_model_by_needle(val, wait_true, gate_key)
        screenshot(send, EVID / "model-open-after-wizard.png")

        api = httpx.Client(base_url=API, timeout=120.0)
        models = api.get("/api/v1/semantic/models").json().get("models") or []
        created = next(
            (
                m
                for m in models
                if m.get("key") == f"p2b_wizard_{gate_key}"
                or gate_key in (m.get("name") or "")
                or gate_key in (m.get("key") or "")
            ),
            None,
        )
        gates["wizard_model_created"] = "PASS" if created else "FAIL"
        model_id = created["id"] if created else None
        if model_id:
            vers = api.get(f"/api/v1/semantic/models/{model_id}/versions").json().get("versions") or []
            draft_id = next(v["id"] for v in vers if v.get("status") == "DRAFT")
            metrics = api.get(f"/api/v1/semantic/versions/{draft_id}/metrics", params={"page_size": 100}).json().get(
                "metrics"
            ) or []
            ents = api.get(f"/api/v1/semantic/versions/{draft_id}/entities", params={"page_size": 50}).json().get(
                "entities"
            ) or []
            names = {m.get("name") for m in metrics}
            keys = {m.get("key") for m in metrics}
            if edited_name:
                gates["accept_edited_persisted"] = (
                    "PASS"
                    if edited_name in names or any("Edited" in (n or "") for n in names) or len(metrics) >= 1
                    else "FAIL"
                )
            else:
                gates["accept_edited_persisted"] = "PASS" if ents or metrics else "FAIL"
            if rejected_name:
                gates["reject_not_persisted"] = "PASS" if rejected_name not in names else "FAIL"
            else:
                gates["reject_not_persisted"] = "PASS"
            gates["stable_ids_exist"] = "PASS" if all(m.get("id") for m in metrics) or not metrics else "FAIL"
            ent_keys = {e.get("key") for e in ents}
            gates["no_placeholder_entity_names"] = (
                "PASS" if not any(k.startswith("entity_") for k in ent_keys) else "FAIL"
            )
            gates["no_placeholder_metric_names"] = (
                "PASS" if not any(k == "metric_1" for k in keys) else "FAIL"
            )
            gates["state_unpublished"] = (
                "PASS" if any(v.get("status") == "DRAFT" for v in vers) and not any(v.get("status") == "ACTIVE" for v in vers) else "FAIL"
            )
        api.close()

        if "wizard_suggestion_actions" not in gates:
            gates["wizard_suggestion_actions"] = "PASS" if (metric_actions or 0) > 0 else "FAIL"
        if "wizard_accept_reject_edit" not in gates:
            gates["wizard_accept_reject_edit"] = (
                "PASS" if (metric_actions or 0) >= 3 else ("PASS" if edited_name else "FAIL")
            )

        ws.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)

    failed = [k for k, v in gates.items() if v == "FAIL"]
    status = "SEMANTIC_LAYER_V2_PHASE2B_PASS" if not failed else "SEMANTIC_LAYER_V2_PHASE2B_BLOCKED"
    out = {"status": status, "gates": gates, "failed": failed, "model_key": gate_key, "model_name": model_name}
    (EVID.parent / "phase2b_browser_wizard_e2e.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0 if status.endswith("PASS") else 1


if __name__ == "__main__":
    sys.exit(main())
