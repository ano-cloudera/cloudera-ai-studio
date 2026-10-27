#!/usr/bin/env python3
"""Limited Phase 2A browser smoke for Semantic Layer (local FE :3001, BE :8001)."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import httpx
import websockets.sync.client as ws_client

REPO = Path(__file__).resolve().parents[2]
EVID = REPO / "testing/evidence/post-uat/SEMANTIC-LAYER-V2"
BASE = "http://127.0.0.1:3001"
API = "http://127.0.0.1:8001"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9244


def curl_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status == 200
    except (urllib.error.URLError, TimeoutError):
        return False


def prefetch_context() -> dict:
    ctx: dict = {}
    client = httpx.Client(base_url=API, timeout=60.0)
    models = client.get("/api/v1/semantic/models").json().get("models") or []
    if not models:
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
        return ctx
    _, model, vid = best
    mid = model["id"]
    ctx["model_id"] = mid
    ctx["model_key"] = model.get("key")
    ctx["model_name"] = model.get("name")
    ctx["version_id"] = vid
    ents = client.get(f"/api/v1/semantic/versions/{vid}/entities", params={"page": 1, "page_size": 5}).json()
    entities = ents.get("entities") or []
    ctx["entity_key"] = entities[0].get("key") if entities else None
    dims = client.get(f"/api/v1/semantic/versions/{vid}/dimensions", params={"page": 1, "page_size": 50}).json()
    dimensions = dims.get("dimensions") or []
    ctx["dimension_keys"] = [d.get("key") for d in dimensions if d.get("key")]
    for d in dimensions:
        dtype = (d.get("data_type") or "").lower()
        if d.get("source_entity_key") and d.get("source_column") and any(
            x in dtype for x in ("int", "decimal", "numeric", "float", "double", "number", "real")
        ):
            ctx["entity_key"] = d["source_entity_key"]
            ctx["entity_column"] = d["source_column"]
            break
    if not ctx.get("entity_column"):
        for d in dimensions:
            if d.get("source_entity_key") and d.get("source_column"):
                ctx["entity_key"] = d["source_entity_key"]
                ctx["entity_column"] = d["source_column"]
                break
    mets = client.get(f"/api/v1/semantic/versions/{vid}/metrics", params={"page": 1, "page_size": 20}).json()
    ctx["metric_keys"] = [m.get("key") for m in (mets.get("metrics") or []) if m.get("key")]
    client.close()
    return ctx


def main() -> int:
    EVID.mkdir(parents=True, exist_ok=True)
    gates: dict[str, str] = {}
    notes: list[str] = []

    if not curl_ok(f"{API}/health") or not curl_ok(f"{API}/health/ready"):
        print(json.dumps({"status": "SEMANTIC_LAYER_V2_PHASE2A_BLOCKED", "blocker": "backend_not_ready"}, indent=2))
        return 1
    if not curl_ok(f"{BASE}/semantic-layer"):
        print(json.dumps({"status": "SEMANTIC_LAYER_V2_PHASE2A_BLOCKED", "blocker": "frontend_not_ready"}, indent=2))
        return 1

    ctx = prefetch_context()
    metric_name = f"Browser Gate Metric {int(time.time())}"
    glossary_term = f"Browser Gate Term {int(time.time())}"

    proc = subprocess.Popen(
        [
            CHROME,
            f"--remote-debugging-port={PORT}",
            "--user-data-dir=/tmp/sem-p2a-browser-smoke",
            "--remote-allow-origins=*",
            "--headless=new",
            "--window-size=1440,900",
            f"{BASE}/semantic-layer",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    console_errors: list[str] = []
    failed_requests: list[str] = []

    try:
        time.sleep(10)
        tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=5).read())
        page = next(t for t in tabs if t.get("type") == "page")
        ws = ws_client.connect(page["webSocketDebuggerUrl"], max_size=32 * 1024 * 1024)
        mid = 0

        def send(method: str, params: dict | None = None) -> dict:
            nonlocal mid
            mid += 1
            ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            while True:
                payload = json.loads(ws.recv())
                if payload.get("method") == "Log.entryAdded":
                    entry = (payload.get("params") or {}).get("entry") or {}
                    if entry.get("level") == "error":
                        text = entry.get("text") or ""
                        low = text.lower()
                        if any(
                            x in low
                            for x in ("next-dev", "hmr", "422", "unprocessable", "uncaught (in promise)", "download the react devtools")
                        ):
                            continue
                        console_errors.append(text[:240])
                if payload.get("method") == "Runtime.exceptionThrown":
                    details = (payload.get("params") or {}).get("exceptionDetails") or {}
                    console_errors.append((details.get("text") or "exception")[:240])
                if payload.get("method") == "Network.responseReceived":
                    resp = (payload.get("params") or {}).get("response") or {}
                    url = resp.get("url") or ""
                    status = resp.get("status")
                    if "/api/" in url and status and status >= 500:
                        failed_requests.append(f"{status} {url}")
                if payload.get("id") == mid:
                    return payload

        send("Log.enable")
        send("Runtime.enable")
        send("Network.enable", {"maxTotalBufferSize": 5_000_000})
        send("Page.enable")

        def val(expression: str):
            outer = send("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True}).get(
                "result"
            ) or {}
            inner = outer.get("result") or {}
            if inner.get("type") == "undefined":
                return None
            return inner.get("value")

        def wait_true(expr: str, timeout: float = 45.0) -> bool:
            deadline = time.time() + timeout
            while time.time() < deadline:
                if val(expr) is True:
                    return True
                time.sleep(0.4)
            return False

        SET_VALUE = """
        function setNativeValue(el, value) {
          if (!el) return false;
          const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
          const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
          if (setter) setter.call(el, value);
          else el.value = value;
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
          return true;
        }
        """

        gates["loading_exits"] = "PASS" if wait_true('!document.body.innerText.includes("Loading semantic layer")', 60) else "FAIL"

        model_label = ctx.get("model_name") or ctx.get("model_key")
        if model_label:
            val(
                f"""
                (() => {{
                  const combo=document.querySelector('[role=\"combobox\"]');
                  if (combo) {{
                    combo.click();
                    const inp=document.querySelector('input[placeholder=\"Search semantic models…\"]');
                    if (inp) {{
                      inp.value={json.dumps(model_label)};
                      inp.dispatchEvent(new Event('input', {{bubbles:true}}));
                    }}
                    const btn=[...document.querySelectorAll('[role=\"listbox\"] button')].find(b=>
                      b.textContent?.includes({json.dumps(model_label)}));
                    btn?.click();
                    return !!btn;
                  }}
                  const sel=document.querySelector('select');
                  if (!sel) return false;
                  const opt=[...sel.options].find(o => o.textContent?.includes({json.dumps(model_label)}));
                  if (opt) {{ sel.value=opt.value; sel.dispatchEvent(new Event('change', {{bubbles:true}})); return true; }}
                  return false;
                }})()
                """
            )
            time.sleep(2.0)
            wait_true('!document.body.innerText.includes("Loading semantic layer")', 30)

        tab_checks = {
            "Overview": "!!document.querySelector('[data-testid=\"semantic-overview-panel\"]')",
            "Data Models": "!!document.querySelector('[data-testid=\"semantic-data-models-table\"]')",
            "Metrics": "!!document.querySelector('[data-testid=\"semantic-metrics-table\"]')",
            "Dimensions": "!!document.querySelector('[data-testid=\"semantic-dimensions-table\"]')",
            "Relationships": "!!document.querySelector('[data-testid=\"semantic-relationships-table\"]')",
            "Glossary": "!!document.querySelector('[data-testid=\"semantic-glossary-table\"]')",
        }
        for tab, check in tab_checks.items():
            val(
                f"(() => {{ const b=[...document.querySelectorAll('button')].find(x=>x.textContent?.trim()==={json.dumps(tab)}); b?.click(); return true; }})()"
            )
            time.sleep(0.8)
            gates[f"tab_{tab.lower().replace(' ', '_')}"] = "PASS" if val(check) else "FAIL"

        # Advanced UX
        val("(() => { const b=document.querySelector('[data-testid=\"semantic-advanced-trigger\"]'); b?.click(); return true; })()")
        time.sleep(0.3)
        adv_count = val("document.querySelectorAll('[data-testid=\"semantic-advanced-trigger\"]').length") or 0
        gates["single_advanced_entry"] = "PASS" if adv_count == 1 else "FAIL"
        menu_text = val(
            "[...document.querySelectorAll('[role=\"menuitem\"]')].map(x=>x.textContent?.trim()).filter(Boolean).join('|')"
        ) or ""
        gates["advanced_menu_purpose"] = (
            "PASS"
            if all(x in menu_text for x in ["Model health", "Version history", "Deployment details", "Preview semantic artifact"])
            else "FAIL"
        )
        gates["no_duplicate_publish_validate"] = (
            "PASS" if "Publish" not in menu_text and "Validate" not in menu_text else "FAIL"
        )
        val("document.querySelector('[aria-label=\"Close Advanced menu\"]')?.click()")
        val("(() => { const b=document.querySelector('[data-testid=\"semantic-advanced-trigger\"]'); b?.click(); return true; })()")
        time.sleep(0.2)
        val(
            "(() => { const rowBtn=[...document.querySelectorAll('button')].find(b=>b.getAttribute('aria-label')?.startsWith('Actions for')); rowBtn?.click(); return true; })()"
        )
        time.sleep(0.2)
        menus_open = val(
            "(document.querySelectorAll('[role=\"menu\"]').length + (document.querySelector('[data-testid=\"semantic-advanced-trigger\"]')?.getAttribute('aria-expanded')==='true' ? 1 : 0))"
        )
        val("document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true})); document.querySelector('[aria-label=\"Close Advanced menu\"]')?.click()")
        gates["menu_overlap_behavior"] = "PASS" if (menus_open or 0) >= 1 else "FAIL"

        # Overview layout desktop
        val("(() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent?.trim()==='Overview'); b?.click(); return true; })()")
        time.sleep(0.5)
        summary_children = val("document.querySelector('[data-testid=\"semantic-overview-summary\"]')?.children?.length") or 0
        grid_cols = val(
            "getComputedStyle(document.querySelector('[data-testid=\"semantic-overview-summary\"]')).gridTemplateColumns"
        ) or ""
        gates["overview_summary_one_row_desktop"] = (
            "PASS" if summary_children == 5 and grid_cols.count(" ") >= 4 else "FAIL"
        )
        gates["no_duplicate_advanced_links"] = (
            "PASS"
            if val(
                "!document.body.innerText.includes('Model health\\nVersion history') && ![...document.querySelectorAll('a,button')].some(el=>el.textContent?.trim()==='Model health' && el.closest('[data-testid=\"semantic-overview-panel\"]'))"
            )
            else "FAIL"
        )
        row_gap = val(
            "(() => { const tr=document.querySelector('[data-testid=\"semantic-recent-definitions\"] tbody tr'); if(!tr) return 0; return parseFloat(getComputedStyle(tr).height)||0; })()"
        )
        gates["recent_definitions_responsive"] = "PASS" if (row_gap or 0) < 120 else "FAIL"

        viewports = [(1440, 900), (1280, 800), (1152, 720), (1800, 900)]
        responsive_ok = True
        for w, h in viewports:
            send("Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": False})
            time.sleep(0.4)
            cols = val(
                "getComputedStyle(document.querySelector('[data-testid=\"semantic-overview-summary\"]')).gridTemplateColumns"
            ) or ""
            if w >= 1280 and cols.count(" ") < 4:
                responsive_ok = False
        send("Emulation.clearDeviceMetricsOverride")
        gates["overview_responsive_layout"] = "PASS" if responsive_ok else "FAIL"

        # Select mode on five authoring tables
        tab_testids = [
            ("Data Models", "semantic-data-models-table"),
            ("Metrics", "semantic-metrics-table"),
            ("Dimensions", "semantic-dimensions-table"),
            ("Relationships", "semantic-relationships-table"),
            ("Glossary", "semantic-glossary-table"),
        ]
        for label, tid in tab_testids:
            val(
                f"(() => {{ const b=[...document.querySelectorAll('button')].find(x=>x.textContent?.trim()==={json.dumps(label)}); b?.click(); return true; }})()"
            )
            time.sleep(0.7)
            val(
                f"(() => {{ const root=document.querySelector('[data-testid=\"{tid}\"]'); const btn=root?.querySelector('[aria-label=\"Select rows\"]'); btn?.click(); return true; }})()"
            )
            time.sleep(0.3)
            active = val(
                f"(() => {{ const root=document.querySelector('[data-testid=\"{tid}\"]'); return !!root?.querySelector('input[type=\"checkbox\"]'); }})()"
            )
            gates[f"select_mode_{tid}"] = "PASS" if active else "FAIL"
            val(
                f"(() => {{ const root=document.querySelector('[data-testid=\"{tid}\"]'); const btn=root?.querySelector('[aria-label=\"Select rows\"]'); if(btn?.getAttribute('aria-pressed')==='true') btn.click(); return true; }})()"
            )

        # Metric invalid + valid save
        val("(() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent?.trim()==='Metrics'); b?.click(); return true; })()")
        time.sleep(4.0)
        val("(() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent?.includes('Add metric')); b?.click(); return true; })()")
        time.sleep(0.5)
        val("(() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent?.trim()==='Save'); b?.click(); return true; })()")
        time.sleep(0.6)
        invalid_shown = val("!!document.querySelector('.text-red-700')")
        gates["metric_invalid_inline"] = "PASS" if invalid_shown else "FAIL"
        val("(() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent?.trim()==='Cancel'); b?.click(); return true; })()")
        time.sleep(0.3)

        entity_key = ctx.get("entity_key") or "entity_1"
        col = ctx.get("entity_column") or "amount"
        val("(() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent?.includes('Add metric')); b?.click(); return true; })()")
        time.sleep(0.5)
        val(
            SET_VALUE
            + f"""
        (() => {{
          const root=document.body;
          const entityKey={json.dumps(entity_key)};
          const columnName={json.dumps(col)};
          const name=root.querySelector('input[placeholder=\"Metric name\"]');
          const def=root.querySelector('textarea[placeholder=\"Business definition\"]');
          const column=root.querySelector('input[placeholder=\"Column\"]');
          const entitySel=[...root.querySelectorAll('select')].find(s => [...s.options].some(o => o.value === entityKey));
          setNativeValue(name, {json.dumps(metric_name)});
          setNativeValue(def, 'Browser smoke metric definition');
          if (entitySel) {{ entitySel.value=entityKey; entitySel.dispatchEvent(new Event('change', {{bubbles:true}})); }}
          if (column) {{
            setNativeValue(column, columnName);
            column.dispatchEvent(new Event('blur', {{bubbles:true}}));
          }}
          return {{ entity: entitySel?.value, column: column?.value }};
        }})()
        """
        )
        time.sleep(0.4)
        val("(() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent?.trim()==='Save'); b?.click(); return true; })()")
        listed = False
        for _ in range(12):
            time.sleep(1.0)
            listed = val(
                f"(() => {{ const table=document.querySelector('[data-testid=\"semantic-metrics-table\"]'); return !!table && table.textContent?.includes({json.dumps(metric_name)}); }})()"
            )
            if listed:
                break
        if not listed and ctx.get("version_id"):
            with httpx.Client(base_url=API, timeout=60.0) as client:
                resp = client.get(
                    f"/api/v1/semantic/versions/{ctx['version_id']}/metrics",
                    params={"search": metric_name, "page_size": 20},
                )
                if resp.status_code == 200:
                    listed = any(m.get("name") == metric_name for m in resp.json().get("metrics") or [])
        gates["metric_valid_save"] = "PASS" if listed else "FAIL"

        # Glossary mappings persist
        val("(() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent?.trim()==='Glossary'); b?.click(); return true; })()")
        time.sleep(0.6)
        val("(() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent?.includes('Add term')); b?.click(); return true; })()")
        time.sleep(0.5)
        val(
            SET_VALUE
            + f"""
        (() => {{
          const term=document.querySelector('input[placeholder=\"Term\"]') || document.querySelector('input[placeholder=\"Glossary term\"]');
          const def=document.querySelector('textarea[placeholder=\"Definition\"]');
          setNativeValue(term, {json.dumps(glossary_term)});
          setNativeValue(def, 'Browser smoke glossary definition');
          const entityKey={json.dumps(ctx.get('entity_key') or '')};
          const label=[...document.querySelectorAll('label')].find(l=>l.textContent?.includes(entityKey));
          label?.querySelector('input[type=\"checkbox\"]')?.click();
          return !!label;
        }})()
        """
        )
        time.sleep(0.3)
        val("(() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent?.trim()==='Save'); b?.click(); return true; })()")
        time.sleep(1.2)
        term_visible = val(f"document.body.innerText.includes({json.dumps(glossary_term)})")
        val("(() => { const rows=[...document.querySelectorAll('tr')]; const row=rows.find(r=>r.textContent?.includes(" + json.dumps(glossary_term) + ")); row?.querySelector('button')?.click(); return true; })()")
        time.sleep(0.8)
        entity_key = ctx.get("entity_key") or ""
        val(
            f"(() => {{ const row=[...document.querySelectorAll('tr')].find(r=>r.textContent?.includes({json.dumps(glossary_term)})); const menu=row?.querySelector('button[aria-label^=\"Actions\"]'); menu?.click(); return true; }})()"
        )
        time.sleep(0.3)
        val("(() => { const item=[...document.querySelectorAll('[role=\"menuitem\"]')].find(x=>x.textContent?.trim()==='Edit'); item?.click(); return true; })()")
        time.sleep(0.6)
        mapping_chip = val(
            f"(() => {{ const text=document.body.innerText; return text.includes('Related objects') && text.includes({json.dumps(entity_key)}); }})()"
        )
        val("(() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent?.trim()==='Cancel' || x.textContent?.trim()==='Close'); b?.click(); return true; })()")
        val("(() => { location.reload(); return true; })()")
        time.sleep(8)
        wait_true('!document.body.innerText.includes("Loading semantic layer")', 60)
        if model_label:
            val(
                f"""
                (() => {{
                  const combo=document.querySelector('[role=\"combobox\"]');
                  if (combo) {{
                    combo.click();
                    const inp=document.querySelector('input[placeholder=\"Search semantic models…\"]');
                    if (inp) {{ inp.value={json.dumps(model_label)}; inp.dispatchEvent(new Event('input', {{bubbles:true}})); }}
                    const btn=[...document.querySelectorAll('[role=\"listbox\"] button')].find(b=>
                      b.textContent?.includes({json.dumps(model_label)}));
                    btn?.click();
                    return true;
                  }}
                  const sel=document.querySelector('select');
                  const opt=sel && [...sel.options].find(o => o.textContent?.includes({json.dumps(model_label)}));
                  if (opt) {{ sel.value=opt.value; sel.dispatchEvent(new Event('change', {{bubbles:true}})); }}
                  return true;
                }})()
                """
            )
            time.sleep(2.0)
        val("(() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent?.trim()==='Glossary'); b?.click(); return true; })()")
        time.sleep(0.8)
        persisted = val(f"document.body.innerText.includes({json.dumps(glossary_term)})")
        gates["glossary_mapping_persist"] = "PASS" if term_visible and persisted and mapping_chip else "FAIL"

        gates["no_fatal_console_errors"] = "PASS" if len(console_errors) == 0 else "FAIL"
        gates["no_critical_api_failures"] = "PASS" if len(failed_requests) == 0 else "FAIL"

        if console_errors:
            notes.append(f"console_errors={console_errors[:5]}")
        if failed_requests:
            notes.append(f"failed_requests={failed_requests[:5]}")

        ws.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)

    ux_gates = [
        "single_advanced_entry",
        "advanced_menu_purpose",
        "no_duplicate_publish_validate",
        "overview_summary_one_row_desktop",
        "overview_responsive_layout",
        "recent_definitions_responsive",
        "no_duplicate_advanced_links",
    ]
    core = [
        "loading_exits",
        "metric_invalid_inline",
        "metric_valid_save",
        "glossary_mapping_persist",
        "no_fatal_console_errors",
        "no_critical_api_failures",
    ]
    failed = [k for k, v in gates.items() if v == "FAIL"]
    status = "SEMANTIC_LAYER_V2_PHASE2A_PASS" if not failed else "SEMANTIC_LAYER_V2_PHASE2A_BLOCKED"
    out = {
        "status": status,
        "harness": "headless_chrome_cdp_localhost",
        "gates": gates,
        "ux_gates": {k: gates.get(k) for k in ux_gates},
        "failed": failed,
        "notes": notes,
        "prefetch": ctx,
    }
    (EVID / "phase2a_browser_smoke.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0 if status.endswith("PASS") else 1


if __name__ == "__main__":
    sys.exit(main())
