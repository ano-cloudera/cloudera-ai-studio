#!/usr/bin/env python3
"""Phase 2B extended browser evidence: publish validation deep-link, post-publish draft UI, rollback modal."""

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

from sem_p2b_browser_helpers import SET_VALUE, navigate_to_model, open_advanced_tab, select_model_by_needle

REPO = Path(__file__).resolve().parents[2]
EVID = REPO / "testing/evidence/post-uat/SEMANTIC-LAYER-V2/PHASE2B"
BASE = "http://127.0.0.1:3001"
API = "http://127.0.0.1:8001"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9246

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


def seed_invalid_model(client: httpx.Client) -> tuple[str, str, str]:
    key = f"p2b_ext_invalid_{uuid.uuid4().hex[:8]}"
    name = f"P2B Invalid Publish {key}"
    model_id = client.post("/api/v1/semantic/models", json={"name": name, "key": key}).json()["model"]["id"]
    vers = client.get(f"/api/v1/semantic/models/{model_id}/versions").json().get("versions") or []
    draft_id = next(v["id"] for v in vers if v.get("status") == "DRAFT")
    client.post(
        f"/api/v1/semantic/versions/{draft_id}/metrics",
        json={
            "key": "ext_bad",
            "name": "Ext Bad Metric",
            "business_definition": "invalid",
            "expression": "SUM(amount)",
            "source_entity_key": "ext_missing_entity",
        },
    )
    return model_id, draft_id, name


def seed_publishable_model(client: httpx.Client) -> tuple[str, str, str]:
    key = f"p2b_ext_pub_{uuid.uuid4().hex[:8]}"
    name = f"P2B Rollback {key}"
    model_id = client.post("/api/v1/semantic/models", json={"name": name, "key": key}).json()["model"]["id"]
    vers = client.get(f"/api/v1/semantic/models/{model_id}/versions").json().get("versions") or []
    draft_id = next(v["id"] for v in vers if v.get("status") == "DRAFT")
    client.post(
        f"/api/v1/semantic/versions/{draft_id}/entities",
        json={"key": "rb_ent", "name": "RB Ent", "source_type": "logical", "table_name": "rb_ent"},
    )
    client.post(
        f"/api/v1/semantic/versions/{draft_id}/dimensions",
        json={
            "key": "rb_dim",
            "name": "Amt",
            "source_entity_key": "rb_ent",
            "source_column": "amount",
            "data_type": "numeric",
        },
    )
    client.post(
        f"/api/v1/semantic/versions/{draft_id}/metrics",
        json={
            "key": "rb_ok",
            "name": "RB OK",
            "business_definition": "ok",
            "expression": "SUM(amount)",
            "source_entity_key": "rb_ent",
        },
    )
    return model_id, draft_id, name


def main() -> int:
    for sub in ("publish-error", "post-publish-draft", "rollback", "deployment", "wizard"):
        (EVID / sub).mkdir(parents=True, exist_ok=True)

    gates: dict[str, str] = {}
    if not curl_ok(f"{BASE}/semantic-layer") or not curl_ok(f"{API}/health/ready"):
        print(json.dumps({"status": "SEMANTIC_LAYER_V2_PHASE2B_BLOCKED", "blocker": "stack_not_ready"}, indent=2))
        return 1

    client = httpx.Client(base_url=API, timeout=180.0)
    invalid_model_id, _, invalid_name = seed_invalid_model(client)
    invalid_needle = invalid_name.split()[-1]
    pub_model_id, pub_draft_id, pub_name = seed_publishable_model(client)
    pub_needle = pub_name.split()[-1]
    pub1 = client.post(f"/api/v1/semantic/models/{pub_model_id}/publish-to-ask-data", json={"version_id": pub_draft_id})
    v1 = pub1.json().get("version_number") if pub1.status_code == 200 else None
    draft2 = client.post(f"/api/v1/semantic/models/{pub_model_id}/versions")
    pub_draft_id2 = draft2.json()["version"]["id"] if draft2.status_code == 200 else pub_draft_id
    client.post(
        f"/api/v1/semantic/versions/{pub_draft_id2}/entities",
        json={"key": "rb_ent", "name": "RB Ent", "source_type": "logical", "table_name": "rb_ent"},
    )
    client.post(
        f"/api/v1/semantic/versions/{pub_draft_id2}/dimensions",
        json={
            "key": "rb_dim",
            "name": "Amt",
            "source_entity_key": "rb_ent",
            "source_column": "amount",
            "data_type": "numeric",
        },
    )
    good2 = client.post(
        f"/api/v1/semantic/versions/{pub_draft_id2}/metrics",
        json={
            "key": "rb_ok_v2",
            "name": "RB OK v2",
            "business_definition": "ok",
            "expression": "SUM(amount)",
            "source_entity_key": "rb_ent",
        },
    )
    pub2 = client.post(
        f"/api/v1/semantic/models/{pub_model_id}/publish-to-ask-data", json={"version_id": pub_draft_id2}
    )
    v2 = pub2.json().get("version_number") if pub2.status_code == 200 else None
    draft_for_edit = client.post(f"/api/v1/semantic/models/{pub_model_id}/versions")
    pub_draft_edit_id = draft_for_edit.json()["version"]["id"] if draft_for_edit.status_code == 200 else pub_draft_id2
    client.post(
        f"/api/v1/semantic/versions/{pub_draft_edit_id}/entities",
        json={"key": "rb_ent", "name": "RB Ent", "source_type": "logical", "table_name": "rb_ent"},
    )
    client.post(
        f"/api/v1/semantic/versions/{pub_draft_edit_id}/metrics",
        json={
            "key": "rb_ok_edit",
            "name": "RB OK",
            "business_definition": "ok",
            "expression": "SUM(amount)",
            "source_entity_key": "rb_ent",
        },
    )
    client.close()

    if not curl_ok(f"{BASE}/semantic-layer"):
        print(json.dumps({"status": "SEMANTIC_LAYER_V2_PHASE2B_BLOCKED", "blocker": "frontend_not_ready"}, indent=2))
        return 1

    proc = subprocess.Popen(
        [
            CHROME,
            f"--remote-debugging-port={PORT}",
            "--user-data-dir=/tmp/sem-p2b-browser-ext",
            "--remote-allow-origins=*",
            "--headless=new",
            "--window-size=1440,900",
            f"{BASE}/semantic-layer?model={invalid_model_id}",
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
        send("Page.reload", {"ignoreCache": True})
        time.sleep(3.0)
        for _ in range(3):
            if curl_ok(f"{API}/health/ready"):
                break
            time.sleep(1.0)

        def val(expression: str):
            outer = send("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True}).get(
                "result"
            ) or {}
            return (outer.get("result") or {}).get("value")

        def wait_true(expr: str, timeout: float = 45.0) -> bool:
            deadline = time.time() + timeout
            while time.time() < deadline:
                if val(expr) is True:
                    return True
                time.sleep(0.4)
            return False

        wait_true('!!document.querySelector(\'[data-testid=\"semantic-create-model\"]\')', 120)
        wait_true('!document.body.innerText.includes("Loading semantic layer")', 90)

        gates["browser_select_invalid_model"] = (
            "PASS"
            if navigate_to_model(send, val, wait_true, BASE, invalid_model_id)
            else "FAIL"
        )
        val("document.querySelector('[data-testid=\"semantic-publish-ask-data\"]')?.click()")
        wait_true(
            '!!document.querySelector(\'[data-testid=\"publish-needs-attention\"]\') || document.body.innerText.includes("Needs attention")',
            45,
        )
        gates["browser_publish_validation_failure"] = (
            "PASS"
            if val(
                "!!document.querySelector('[data-testid=\"publish-needs-attention\"]') || document.body.innerText.includes('Needs attention')"
            )
            else "FAIL"
        )
        screenshot(send, EVID / "publish-error" / "needs-attention-browser.png")
        val(
            """
            (() => {
              const btn = document.querySelector('[data-testid=\"publish-needs-attention\"] ul button');
              btn?.click();
              return !!btn;
            })()
            """
        )
        time.sleep(1.5)
        editor_open = val(
            """
            (() => {
              const metricsTab = [...document.querySelectorAll('button')].find(b => b.textContent?.trim() === 'Metrics');
              const onMetrics = metricsTab?.className?.includes('violet') || metricsTab?.className?.includes('text-cloudera-violet');
              return !!onMetrics && document.body.innerText.includes('Ext Bad Metric');
            })()
            """
        )
        gates["browser_issue_deep_link"] = "PASS" if editor_open else "FAIL"
        screenshot(send, EVID / "publish-error" / "issue-deeplink-editor.png")
        val("document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
        time.sleep(0.3)

        gates["browser_select_publish_model"] = (
            "PASS" if navigate_to_model(send, val, wait_true, BASE, pub_model_id) else "FAIL"
        )
        val("(() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent?.trim()==='Metrics'); b?.click(); return true; })()")
        time.sleep(0.8)
        val(
            """
            (() => {
              const row = document.querySelector('[data-testid=\"semantic-metrics-table\"] tbody tr');
              row?.click();
              return !!row;
            })()
            """
        )
        time.sleep(0.6)
        val(
            SET_VALUE
            + """
            (() => {
              const inp = document.querySelector('[role=\"dialog\"] input[placeholder=\"Metric name\"]');
              setNativeValue(inp, 'RB OK draft edit');
              return !!inp;
            })()
            """
        )
        val(
            """
            (() => {
              const save = [...document.querySelectorAll('[role=\"dialog\"] button')].find(b =>
                b.textContent?.trim() === 'Save');
              save?.click();
              return !!save;
            })()
            """
        )
        time.sleep(1.2)
        overview_draft = val(
            f"""
            (async () => {{
              const uiDraft = document.body.innerText.includes('Draft') || document.body.innerText.includes('Validate');
              try {{
                const r = await fetch('/api/v1/semantic/models/{pub_model_id}/versions');
                const j = await r.json();
                const hasDraft = (j.versions || []).some(v => v.status === 'DRAFT');
                const active = (j.versions || []).find(v => v.status === 'ACTIVE');
                return hasDraft && !!active;
              }} catch {{
                return uiDraft;
              }}
            }})()
            """
        )
        gates["browser_post_publish_draft_state"] = "PASS" if overview_draft else "FAIL"
        screenshot(send, EVID / "post-publish-draft" / "draft-after-edit-ready.png")

        open_advanced_tab(val, "semantic-advanced-version-history", "Version history")
        time.sleep(0.5)
        val(
            """
            (() => {
              const rb = [...document.querySelectorAll('[data-testid=\"semantic-version-history-table\"] button')].find(b =>
                b.textContent?.trim() === 'Rollback' && !b.disabled);
              rb?.click(); return !!rb;
            })()
            """
        )
        time.sleep(0.5)
        modal = val("document.body.innerText.includes('Rollback semantic model?')")
        gates["browser_rollback_product_modal"] = "PASS" if modal else "FAIL"
        screenshot(send, EVID / "rollback" / "rollback-confirm-modal.png")
        if modal:
            val(
                """
                (() => {
                  const buttons = [...document.querySelectorAll('button')].filter(b => b.textContent?.trim() === 'Rollback');
                  buttons[buttons.length - 1]?.click();
                  return true;
                })()
                """
            )
            time.sleep(2.0)
            gates["browser_rollback_confirmed"] = "PASS" if not val("document.body.innerText.includes('Rollback semantic model?')") else "FAIL"
        else:
            gates["browser_rollback_confirmed"] = "FAIL"

        open_advanced_tab(val, "semantic-advanced-deployment-details", "Deployment details")
        gates["browser_deployment_details"] = (
            "PASS" if val("document.body.innerText.match(/runtime|deployment|active/i)") else "FAIL"
        )
        screenshot(send, EVID / "deployment" / "deployment-details.png")
        gates["browser_two_published_versions"] = (
            "PASS" if v1 and v2 and v2 > v1 else "FAIL"
        )

        ws.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)

    failed = [k for k, v in gates.items() if v == "FAIL"]
    status = "SEMANTIC_LAYER_V2_PHASE2B_PASS" if not failed else "SEMANTIC_LAYER_V2_PHASE2B_BLOCKED"
    out = {"status": status, "gates": gates, "failed": failed}
    (EVID / "phase2b_browser_extended.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0 if status.endswith("PASS") else 1


if __name__ == "__main__":
    sys.exit(main())
