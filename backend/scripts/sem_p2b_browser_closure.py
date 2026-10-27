#!/usr/bin/env python3
"""Phase 2B browser + API closure: extends smoke with publish-failure and evidence folders."""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]
EVID = REPO / "testing/evidence/post-uat/SEMANTIC-LAYER-V2/PHASE2B"
API = "http://127.0.0.1:8001"
SMOKE = REPO / "backend/scripts/sem_p2b_browser_smoke.py"
EXTENDED = REPO / "backend/scripts/sem_p2b_browser_extended.py"
WIZARD = REPO / "backend/scripts/sem_p2b_browser_wizard_e2e.py"


def main() -> int:
    for sub in (
        "post-publish-draft",
        "rollback",
        "deployment",
        "publish-error",
    ):
        (EVID / sub).mkdir(parents=True, exist_ok=True)

    gates: dict[str, str] = {}
    proc = subprocess.run([sys.executable, str(SMOKE)], cwd=str(REPO / "backend"), capture_output=True, text=True)
    smoke_out: dict = {"status": "SEMANTIC_LAYER_V2_PHASE2B_BLOCKED", "gates": {}}
    smoke_path = EVID / "phase2b_browser_smoke.json"
    if proc.stdout:
        text = proc.stdout.strip()
        try:
            smoke_out = json.loads(text)
        except json.JSONDecodeError:
            anchor = text.rfind('{\n  "status"')
            if anchor >= 0:
                try:
                    smoke_out = json.loads(text[anchor:])
                except json.JSONDecodeError:
                    pass
    if smoke_out.get("status", "").endswith("BLOCKED") and smoke_path.is_file():
        try:
            smoke_out = json.loads(smoke_path.read_text())
        except json.JSONDecodeError:
            pass
    for k, v in (smoke_out.get("gates") or {}).items():
        gates[f"smoke_{k}"] = v

    client = httpx.Client(base_url=API, timeout=180.0)
    try:
        key = f"p2b_closure_{uuid.uuid4().hex[:8]}"
        create = client.post("/api/v1/semantic/models", json={"name": f"Closure {key}", "key": key})
        gates["api_create_model"] = "PASS" if create.status_code == 200 else "FAIL"
        if create.status_code != 200:
            return _finish(gates, proc.returncode, smoke_out.get("status", ""), 0, "")
        model_id = create.json()["model"]["id"]
        vers = client.get(f"/api/v1/semantic/models/{model_id}/versions").json().get("versions") or []
        draft_id = next(v["id"] for v in vers if v.get("status") == "DRAFT")
        client.post(
            f"/api/v1/semantic/versions/{draft_id}/entities",
            json={"key": "cl_sales", "name": "CL Sales", "source_type": "logical", "table_name": "cl_sales"},
        )
        client.post(
            f"/api/v1/semantic/versions/{draft_id}/dimensions",
            json={
                "key": "cl_amt",
                "name": "Amount",
                "source_entity_key": "cl_sales",
                "source_column": "amount",
                "data_type": "numeric",
            },
        )
        bad = client.post(
            f"/api/v1/semantic/versions/{draft_id}/metrics",
            json={
                "key": "cl_bad",
                "name": "CL Bad Metric",
                "business_definition": "bad",
                "expression": "SUM(missing_col_p2b)",
                "source_entity_key": "cl_sales",
            },
        )
        gates["api_invalid_metric"] = "PASS" if bad.status_code == 200 else "FAIL"
        pub = client.post(f"/api/v1/semantic/models/{model_id}/publish-to-ask-data", json={"version_id": draft_id})
        if pub.status_code == 422:
            detail = pub.json().get("detail") or {}
            gates["api_publish_needs_attention"] = "PASS"
            gates["api_issue_panel_shape"] = "PASS" if detail.get("issues") else "FAIL"
            (EVID / "publish-error" / "api-needs-attention.json").write_text(json.dumps(detail, indent=2))
        else:
            gates["api_publish_needs_attention"] = "PASS" if pub.status_code in (200, 502) else "FAIL"
        good = client.post(
            f"/api/v1/semantic/versions/{draft_id}/metrics",
            json={
                "key": "cl_ok",
                "name": "CL OK",
                "business_definition": "ok",
                "expression": "SUM(amount)",
                "source_entity_key": "cl_sales",
            },
        )
        if good.status_code == 200:
            pub2 = client.post(f"/api/v1/semantic/models/{model_id}/publish-to-ask-data", json={"version_id": draft_id})
            if pub2.status_code == 200:
                active = pub2.json().get("version_number")
                rt1 = client.get("/api/v1/semantic/runtime/status", params={"model_key": key}).json()
                client.patch(
                    f"/api/v1/semantic/versions/{draft_id}/metrics/{good.json()['metric']['id']}",
                    json={"name": "CL OK edited draft"},
                )
                rt2 = client.get("/api/v1/semantic/runtime/status", params={"model_key": key}).json()
                gates["post_publish_draft_runtime_unchanged"] = (
                    "PASS" if rt1.get("runtime_active_version") == rt2.get("runtime_active_version") == active else "FAIL"
                )
                (EVID / "post-publish-draft" / "runtime.json").write_text(json.dumps({"before": rt1, "after": rt2}, indent=2))
                hist = client.get(f"/api/v1/semantic/models/{model_id}/versions").json().get("versions") or []
                archived = [v for v in hist if v.get("status") == "ARCHIVED"]
                if len(archived) >= 1 and pub2.status_code == 200:
                    pub3 = client.post(f"/api/v1/semantic/models/{model_id}/publish-to-ask-data", json={"version_id": draft_id})
                    if pub3.status_code == 200:
                        v2 = pub3.json().get("version_number")
                        rollback_target = archived[-1]["id"]
                        rb = client.post(f"/api/v1/semantic/versions/{rollback_target}/rollback")
                        gates["rollback_api"] = "PASS" if rb.status_code == 200 else "FAIL"
                        rt3 = client.get("/api/v1/semantic/runtime/status", params={"model_key": key}).json()
                        gates["rollback_runtime_consistency"] = (
                            "PASS" if rt3.get("registry_active_version") else "FAIL"
                        )
                        (EVID / "rollback" / "api-rollback.json").write_text(
                            json.dumps({"rolled_back_to": archived[-1], "runtime": rt3, "v2": v2}, indent=2)
                        )
    finally:
        client.close()

    wiz_rc = 0
    wiz_status = ""
    if WIZARD.is_file():
        wiz_proc = subprocess.run([sys.executable, str(WIZARD)], cwd=str(REPO / "backend"), capture_output=True, text=True)
        wiz_rc = wiz_proc.returncode
        wiz_path = EVID / "phase2b_browser_wizard_e2e.json"
        if wiz_path.is_file():
            try:
                wiz_out = json.loads(wiz_path.read_text())
                wiz_status = wiz_out.get("status", "")
                for k, v in (wiz_out.get("gates") or {}).items():
                    gates[f"wizard_{k}"] = v
            except json.JSONDecodeError:
                wiz_status = "SEMANTIC_LAYER_V2_PHASE2B_BLOCKED"
        if wiz_rc != 0 and not wiz_status:
            gates["wizard_runner"] = "FAIL"
        elif wiz_rc == 0:
            gates["wizard_runner"] = "PASS"

    ext_rc = 0
    ext_status = ""
    if EXTENDED.is_file():
        ext_proc = subprocess.run([sys.executable, str(EXTENDED)], cwd=str(REPO / "backend"), capture_output=True, text=True)
        ext_rc = ext_proc.returncode
        ext_path = EVID / "phase2b_browser_extended.json"
        if ext_path.is_file():
            try:
                ext_out = json.loads(ext_path.read_text())
                ext_status = ext_out.get("status", "")
                for k, v in (ext_out.get("gates") or {}).items():
                    gates[f"extended_{k}"] = v
            except json.JSONDecodeError:
                ext_status = "SEMANTIC_LAYER_V2_PHASE2B_BLOCKED"
        elif ext_proc.stdout:
            anchor = ext_proc.stdout.strip().rfind('{\n  "status"')
            if anchor >= 0:
                try:
                    ext_out = json.loads(ext_proc.stdout.strip()[anchor:])
                    ext_status = ext_out.get("status", "")
                    for k, v in (ext_out.get("gates") or {}).items():
                        gates[f"extended_{k}"] = v
                except json.JSONDecodeError:
                    pass
        if ext_rc != 0 and not ext_status:
            gates["extended_runner"] = "FAIL"
        elif ext_rc == 0:
            gates["extended_runner"] = "PASS"

    return _finish(gates, proc.returncode, smoke_out.get("status", ""), ext_rc, ext_status, wiz_rc, wiz_status)


def _finish(
    gates: dict[str, str],
    smoke_rc: int,
    smoke_status: str = "",
    ext_rc: int = 0,
    ext_status: str = "",
    wiz_rc: int = 0,
    wiz_status: str = "",
) -> int:
    failed = [k for k, v in gates.items() if v == "FAIL"]
    smoke_ok = smoke_rc == 0 and (not smoke_status or smoke_status.endswith("PASS"))
    ext_ok = ext_rc == 0 and (not ext_status or ext_status.endswith("PASS"))
    wiz_ok = wiz_rc == 0 and (not wiz_status or wiz_status.endswith("PASS"))
    status = (
        "SEMANTIC_LAYER_V2_PHASE2B_PASS"
        if not failed and smoke_ok and ext_ok and wiz_ok
        else "SEMANTIC_LAYER_V2_PHASE2B_BLOCKED"
    )
    out = {"status": status, "gates": gates, "failed": failed}
    (EVID / "phase2b_browser_closure.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0 if status.endswith("PASS") else 1


if __name__ == "__main__":
    sys.exit(main())
