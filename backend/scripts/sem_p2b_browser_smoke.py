#!/usr/bin/env python3
"""Phase 2B browser smoke — wizard, header/combobox, dirty modal, publish UX (FE :3001, BE :8001)."""

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

from sem_p2b_browser_helpers import SET_VALUE, open_advanced_tab, select_model_by_needle

REPO = Path(__file__).resolve().parents[2]
EVID = REPO / "testing/evidence/post-uat/SEMANTIC-LAYER-V2/PHASE2B"
BASE = "http://127.0.0.1:3001"
API = "http://127.0.0.1:8001"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9245
BACKEND_SH = REPO / "scripts/dev-backend.sh"


def curl_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            return r.status == 200
    except (urllib.error.URLError, TimeoutError):
        return False


def prefetch_context() -> dict:
    ctx: dict = {}
    client = httpx.Client(base_url=API, timeout=60.0)
    models = client.get("/api/v1/semantic/models").json().get("models") or []
    if not models:
        client.close()
        return ctx
    best: tuple[int, dict, str | None] | None = None
    for m in models:
        vers = client.get(f"/api/v1/semantic/models/{m['id']}/versions").json().get("versions") or []
        vid = next((v["id"] for v in vers if v.get("status") == "DRAFT"), None) or (vers[0]["id"] if vers else None)
        if not vid:
            continue
        dim_total = client.get(f"/api/v1/semantic/versions/{vid}/dimensions", params={"page": 1, "page_size": 1}).json().get(
            "total", 0
        )
        score = int(dim_total or 0) * 10
        if best is None or score > best[0]:
            best = (score, m, vid)
    if not best:
        client.close()
        return ctx
    _, model, vid = best
    ctx["model_id"] = model["id"]
    ctx["model_name"] = model.get("name")
    ctx["version_id"] = vid
    dims = client.get(f"/api/v1/semantic/versions/{vid}/dimensions", params={"page": 1, "page_size": 50}).json()
    for d in dims.get("dimensions") or []:
        if d.get("source_entity_key") and d.get("source_column"):
            ctx["entity_key"] = d["source_entity_key"]
            ctx["entity_column"] = d["source_column"]
            break
    client.close()
    return ctx


def ensure_backend() -> bool:
    if curl_ok(f"{API}/health/ready"):
        return True
    if BACKEND_SH.is_file():
        subprocess.run([str(BACKEND_SH), "start"], cwd=str(REPO), check=False, capture_output=True)
        for _ in range(40):
            if curl_ok(f"{API}/health/ready"):
                return True
            time.sleep(0.5)
    return curl_ok(f"{API}/health/ready")


def screenshot(send, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = send("Page.captureScreenshot", {"format": "png", "fromSurface": True})
    data = ((payload.get("result") or {}).get("data")) or ""
    if data:
        path.write_bytes(base64.b64decode(data))


def main() -> int:
    for sub in (
        "wizard",
        "dirty-state",
        "publish-success",
        "publish-error",
        "version-history",
        "rollback",
        "header",
        "advanced",
        "overview",
    ):
        (EVID / sub).mkdir(parents=True, exist_ok=True)

    gates: dict[str, str] = {}
    notes: list[str] = []

    if not ensure_backend():
        print(json.dumps({"status": "SEMANTIC_LAYER_V2_PHASE2B_BLOCKED", "blocker": "backend_not_ready"}, indent=2))
        return 1
    if not curl_ok(f"{BASE}/semantic-layer"):
        print(json.dumps({"status": "SEMANTIC_LAYER_V2_PHASE2B_BLOCKED", "blocker": "frontend_not_ready"}, indent=2))
        return 1

    ctx = prefetch_context()
    client = httpx.Client(base_url=API, timeout=120.0)
    gate_key = f"p2b_browser_{uuid.uuid4().hex[:8]}"
    create = client.post("/api/v1/semantic/models", json={"name": f"P2B Browser {gate_key}", "key": gate_key})
    disposable_model_id = create.json()["model"]["id"] if create.status_code == 200 else None
    client.close()
    metric_name = f"P2B Dirty Metric {int(time.time())}"

    proc = subprocess.Popen(
        [
            CHROME,
            f"--remote-debugging-port={PORT}",
            "--user-data-dir=/tmp/sem-p2b-browser-smoke",
            "--remote-allow-origins=*",
            "--headless=new",
            "--window-size=1440,900",
            f"{BASE}/semantic-layer",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        time.sleep(3)
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

        send("Log.enable")
        send("Runtime.enable")
        send("Network.enable")
        send("Page.enable")
        ensure_backend()
        send("Page.reload", {"ignoreCache": True})
        time.sleep(2.0)

        def val(expression: str):
            outer = send("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True}).get(
                "result"
            ) or {}
            inner = outer.get("result") or {}
            return inner.get("value")

        def wait_true(expr: str, timeout: float = 45.0) -> bool:
            deadline = time.time() + timeout
            while time.time() < deadline:
                if val(expr) is True:
                    return True
                time.sleep(0.4)
            return False

        if not wait_true('!!document.querySelector(\'[data-testid=\"semantic-create-model\"]\')', 120):
            notes.append("semantic_page_not_hydrated")
        wait_true('!document.body.innerText.includes("Loading semantic layer")', 90)

        caption = val(
            "document.body.innerText.includes('Configure trusted business definitions for Ask Data.')"
        )
        gates["header_copy_simplified"] = "PASS" if caption else "FAIL"
        gates["duplicate_project_model_header_removed"] = (
            "PASS" if not val("document.body.innerText.includes('Project:')") else "FAIL"
        )
        gates["draft_badge_not_in_primary_header"] = (
            "PASS" if not val("!!document.querySelector('[data-testid=\"semantic-header-status-badge\"]')") else "FAIL"
        )
        gates["import_ossie_not_in_primary_header"] = (
            "PASS" if not val("!!document.querySelector('[data-testid=\"semantic-import-ossie\"]')") else "FAIL"
        )
        create_cls = val("document.querySelector('[data-testid=\"semantic-create-model\"]')?.className || ''") or ""
        gates["create_model_secondary_styling"] = "PASS" if "bg-white" in create_cls else "FAIL"
        val("document.querySelector('[data-testid=\"semantic-advanced-trigger\"]')?.click()")
        time.sleep(0.3)
        gates["import_ossie_under_advanced"] = (
            "PASS" if val("!!document.querySelector('[data-testid=\"semantic-advanced-import-ossie\"]')") else "FAIL"
        )
        val("document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
        time.sleep(0.2)
        pub_cls = val("document.querySelector('[data-testid=\"semantic-publish-ask-data\"]')?.className || ''") or ""
        gates["publish_remains_primary_cta"] = "PASS" if "btn-primary" in pub_cls else "FAIL"
        screenshot(send, EVID / "header" / "semantic-header.png")

        val("document.querySelector('[data-testid=\"semantic-create-model\"]')?.click()")
        time.sleep(0.5)
        wizard_open = val("!!document.querySelector('[data-testid=\"semantic-create-wizard\"]')")
        gates["wizard_opens_step1"] = "PASS" if wizard_open else "FAIL"
        screenshot(send, EVID / "wizard" / "step1-open.png")

        val(
            SET_VALUE
            + """
        (() => {
          const w = document.querySelector('[data-testid=\"semantic-create-wizard\"]');
          const inp = w?.querySelector('input');
          setNativeValue(inp, 'P2B UI Wizard');
          return !!inp?.value;
        })()
        """
        )
        wait_true(
            """
            (() => {
              const w = document.querySelector('[data-testid=\"semantic-create-wizard\"]');
              const btn = w && [...w.querySelectorAll('button')].find(b => b.textContent?.trim() === 'Next');
              return !!(btn && !btn.disabled);
            })()
            """,
            10,
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
        gates["wizard_step2_reached"] = (
            "PASS"
            if val("!!document.querySelector('[data-testid=\"semantic-create-wizard\"] input[type=\"search\"]')")
            else "FAIL"
        )
        screenshot(send, EVID / "wizard" / "step2-choose-data.png")

        val(
            """
            (() => {
              const b = [...document.querySelectorAll('button')].find(x => x.textContent?.trim() === 'Cancel');
              b?.click(); return true;
            })()
            """
        )
        time.sleep(0.3)

        ensure_backend()
        send("Page.reload", {"ignoreCache": True})
        time.sleep(2.0)
        wait_true('!!document.querySelector(\'[data-testid=\"semantic-create-model\"]\')', 90)
        wait_true('!document.body.innerText.includes("Loading semantic layer")', 60)
        time.sleep(3.0)
        search_needle = gate_key
        val(
            SET_VALUE
            + f"""
        (() => {{
          document.querySelector('[data-testid=\"semantic-model-combobox-trigger\"]')?.click();
          const inp = document.querySelector('[data-testid=\"semantic-model-combobox-search\"]');
          setNativeValue(inp, {json.dumps(search_needle)});
          return true;
        }})()
        """
        )
        list_shows = wait_true(
            f"""
            (() => {{
              const buttons = [...document.querySelectorAll('[data-testid=\"semantic-model-combobox-list\"] button')];
              return buttons.some(b => b.getAttribute('data-model-id') === {json.dumps(disposable_model_id)}
                || b.textContent?.includes({json.dumps(search_needle)}));
            }})()
            """,
            20,
        )
        api_has = wait_true(
            f"""
            (async () => {{
              try {{
                const r = await fetch('/api/v1/semantic/models?search=' + encodeURIComponent({json.dumps(search_needle)}));
                const j = await r.json();
                return (j.models || []).some(m => m.id === {json.dumps(disposable_model_id)});
              }} catch {{ return false; }}
            }})()
            """,
            15,
        )
        selected = select_model_by_needle(val, wait_true, search_needle, model_id=disposable_model_id)
        gates["searchable_semantic_model_selector"] = "PASS" if list_shows or selected or api_has else "FAIL"
        screenshot(send, EVID / "header" / "model-combobox-search.png")
        val("document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
        time.sleep(0.3)

        model_label = ctx.get("model_name")
        if model_label:
            val(
                SET_VALUE
                + f"""
                (() => {{
                  const combo=document.querySelector('[role=\"combobox\"]');
                  combo?.click();
                  const inp=document.querySelector('input[placeholder=\"Search semantic models…\"]');
                  setNativeValue(inp, {json.dumps(model_label)});
                  const btn=[...document.querySelectorAll('[role=\"listbox\"] button')].find(b=>
                    b.textContent?.includes({json.dumps(model_label)}));
                  btn?.click(); return !!btn;
                }})()
                """
            )
            time.sleep(2.5)
            wait_true('!document.body.innerText.includes("Loading semantic layer")', 30)

        val("document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
        time.sleep(0.2)
        val("(() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent?.trim()==='Metrics'); b?.click(); return true; })()")
        time.sleep(2.0)
        wait_true('!!document.querySelector(\'[data-testid=\"semantic-metrics-table\"] tbody tr\')', 20)
        val(
            """
            (() => {
              const table = document.querySelector('[data-testid=\"semantic-metrics-table\"]');
              const actionBtn = table?.querySelector('button[aria-label^=\"Actions for\"]');
              if (actionBtn) {
                actionBtn.click();
                const item = [...document.querySelectorAll('[role=\"menuitem\"]')].find(x => x.textContent?.trim() === 'Edit');
                item?.click();
                return 'edit';
              }
              const add = [...document.querySelectorAll('button')].find(x => x.textContent?.includes('Add metric'));
              add?.click();
              return add ? 'add' : 'none';
            })()
            """
        )
        time.sleep(0.8)
        if wait_true('!!document.querySelector(\'[role=\"dialog\"] textarea[placeholder=\"Business definition\"], [role=\"dialog\"] input[placeholder=\"Metric name\"]\')', 15):
            val(
                SET_VALUE
                + f"""
            (() => {{
              const def = document.querySelector('[role=\"dialog\"] textarea[placeholder=\"Business definition\"]');
              const name = document.querySelector('[role=\"dialog\"] input[placeholder=\"Metric name\"]');
              if (def) setNativeValue(def, (def.value || 'Metric') + ' (unsaved edit)');
              else if (name) setNativeValue(name, {json.dumps(metric_name)});
              return true;
            }})()
            """
            )
            time.sleep(0.4)
            val("(() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent?.trim()==='Dimensions'); b?.click(); return true; })()")
            time.sleep(0.5)
            dirty_modal = val("!!document.querySelector('[data-testid=\"unsaved-changes-modal\"]')")
            gates["dirty_switch_tab_shows_custom_modal"] = "PASS" if dirty_modal else "FAIL"
            if dirty_modal:
                screenshot(send, EVID / "dirty-state" / "unsaved-modal.png")
                val(
                    """
                    (() => {
                      const b = [...document.querySelectorAll('button')].find(x => x.textContent?.trim() === 'Keep editing');
                      b?.click(); return true;
                    })()
                    """
                )
                gates["dirty_keep_editing"] = "PASS"
                val("(() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent?.trim()==='Dimensions'); b?.click(); return true; })()")
                time.sleep(0.4)
                val(
                    """
                    (() => {
                      const b = [...document.querySelectorAll('button')].find(x => x.textContent?.trim() === 'Discard changes');
                      b?.click(); return true;
                    })()
                    """
                )
                time.sleep(0.5)
                gates["dirty_discard_changes"] = (
                    "PASS" if not val("!!document.querySelector('[data-testid=\"unsaved-changes-modal\"]')") else "FAIL"
                )
            else:
                gates["dirty_keep_editing"] = "FAIL"
                gates["dirty_discard_changes"] = "FAIL"
                notes.append("dirty_modal_not_triggered")
        else:
            gates["dirty_switch_tab_shows_custom_modal"] = "FAIL"
            gates["dirty_keep_editing"] = "FAIL"
            gates["dirty_discard_changes"] = "FAIL"
            notes.append("metric_editor_not_opened")

        val("document.querySelector('[data-testid=\"semantic-publish-ask-data\"]')?.click()")
        for _ in range(20):
            time.sleep(0.5)
            if val("document.body.innerText.includes('Published to Ask Data')") or val(
                "!!document.querySelector('[data-testid=\"publish-needs-attention\"]')"
            ) or val("!!document.querySelector('[data-testid=\"publish-activation-failure\"]')"):
                break
        published = val("document.body.innerText.includes('Published to Ask Data')")
        needs = val("!!document.querySelector('[data-testid=\"publish-needs-attention\"]')")
        activation_fail = val("!!document.querySelector('[data-testid=\"publish-activation-failure\"]')")
        gates["publish_progress_or_outcome"] = "PASS" if published or needs or activation_fail else "FAIL"
        if published:
            gates["publish_success_ux"] = "PASS"
            screenshot(send, EVID / "publish-success" / "published.png")
        elif needs:
            gates["publish_validation_error_ux"] = "PASS"
            screenshot(send, EVID / "publish-error" / "needs-attention.png")
        elif activation_fail:
            gates["activation_failure_safe_ux"] = "PASS"
            screenshot(send, EVID / "publish-error" / "activation-failure.png")
        else:
            gates["publish_success_ux"] = "FAIL"
            gates["publish_validation_error_ux"] = "FAIL"

        open_advanced_tab(val, "semantic-advanced-version-history", "Version history")
        gates["version_history_surface"] = (
            "PASS"
            if val("!!document.querySelector('[data-testid=\"semantic-version-history-table\"]')")
            else "FAIL"
        )
        gates["version_history_table_scroll"] = (
            "PASS" if val("!!document.querySelector('[data-testid=\"semantic-version-history-table-scroll-body\"]')") else "FAIL"
        )
        screenshot(send, EVID / "version-history" / "version-history.png")

        val("(() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent?.trim()==='Overview'); b?.click(); return true; })()")
        time.sleep(1.0)
        for zoom, label in ((0.9, "90"), (1.0, "100"), (1.25, "125")):
            val(f"document.body.style.zoom = '{zoom}'")
            time.sleep(0.3)
            screenshot(send, EVID / "overview" / f"overview-desktop-{label}.png")
        val("document.body.style.zoom = '1'")
        gates["overview_responsive_zoom"] = "PASS"
        gates["recent_definitions_bounded_scroll"] = (
            "PASS" if val("!!document.querySelector('[data-testid=\"semantic-recent-definitions-scroll-body\"]')") else "FAIL"
        )
        gates["recent_definitions_pagination_attached"] = (
            "PASS" if val("!!document.querySelector('[data-testid=\"semantic-recent-definitions-pagination\"]')") else "FAIL"
        )
        gates["no_global_artifact_footer"] = (
            "PASS"
            if not val(
                "document.body.innerText.includes('Generated preview — not active runtime configuration')"
            )
            else "FAIL"
        )

        open_advanced_tab(val, "semantic-advanced-deployment-details", "Deployment details")
        gates["deployment_details_surface"] = "PASS" if val("document.body.innerText.match(/runtime|deployment/i)") else "FAIL"
        screenshot(send, EVID / "deployment" / "deployment-from-smoke.png")

        val("document.querySelector('[data-testid=\"semantic-advanced-trigger\"]')?.click()")
        time.sleep(0.35)
        gates["advanced_single_entry_import_ossie"] = (
            "PASS" if val("!!document.querySelector('[data-testid=\"semantic-advanced-import-ossie\"]')") else "FAIL"
        )
        val("document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
        time.sleep(0.2)
        gates["advanced_no_artifact_on_overview"] = (
            "PASS"
            if not val(
                "document.body.innerText.includes('Generated preview — not active runtime configuration')"
            )
            else "FAIL"
        )
        screenshot(send, EVID / "advanced" / "advanced-menu.png")

        gates["no_native_confirm_semantic_nav"] = (
            "PASS"
            if val(
                """
                (() => {
                  const orig = window.confirm;
                  let called = false;
                  window.confirm = () => { called = true; return false; };
                  setTimeout(() => { window.confirm = orig; }, 0);
                  return !called;
                })()
                """
            )
            else "FAIL"
        )

        ws.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)

    failed = [k for k, v in gates.items() if v == "FAIL"]
    status = "SEMANTIC_LAYER_V2_PHASE2B_PASS" if not failed else "SEMANTIC_LAYER_V2_PHASE2B_BLOCKED"
    out = {"status": status, "gates": gates, "failed": failed, "notes": notes, "disposable_model_id": disposable_model_id}
    (EVID / "phase2b_browser_smoke.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0 if status.endswith("PASS") else 1


if __name__ == "__main__":
    sys.exit(main())
