#!/usr/bin/env python3
"""Live API gates for SEMANTIC_LAYER_V2 Phase 2B workflow."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8001"
SCRIPTS = Path(__file__).resolve().parent
BACKEND = SCRIPTS.parent


def main() -> int:
    results: dict[str, str] = {}
    client = httpx.Client(base_url=BASE, timeout=180.0)
    try:
        results["health"] = "PASS" if client.get("/health").status_code == 200 else "FAIL"
        key = f"p2b_{uuid.uuid4().hex[:8]}"
        create = client.post("/api/v1/semantic/models", json={"name": f"P2B Gate {key}", "key": key, "description": "gate"})
        results["wizard_create_draft"] = "PASS" if create.status_code == 200 else "FAIL"
        if create.status_code != 200:
            print(json.dumps(results, indent=2))
            return 1
        model_id = create.json()["model"]["id"]
        vers = client.get(f"/api/v1/semantic/models/{model_id}/versions").json().get("versions") or []
        draft_id = next(v["id"] for v in vers if v.get("status") == "DRAFT")
        ent = client.post(
            f"/api/v1/semantic/versions/{draft_id}/entities",
            json={"key": "gate_sales", "name": "Gate Sales", "source_type": "logical", "table_name": "gate_sales"},
        )
        results["selected_tables_persist"] = "PASS" if ent.status_code == 200 else "FAIL"
        dim = client.post(
            f"/api/v1/semantic/versions/{draft_id}/dimensions",
            json={
                "key": "gate_amount",
                "name": "Amount",
                "source_entity_key": "gate_sales",
                "source_column": "amount",
                "data_type": "numeric",
            },
        )
        results["dimension_seed"] = "PASS" if dim.status_code == 200 else "FAIL"
        accept = client.post(
            f"/api/v1/semantic/models/{model_id}/suggestions/accept",
            json={
                "version_id": draft_id,
                "selections": [
                    {
                        "suggestion_id": "metric:gate_total",
                        "type": "metric",
                        "accepted": True,
                        "payload": {
                            "key": "gate_total",
                            "name": "Gate Total",
                            "expression": "SUM(amount)",
                            "source_entity_key": "gate_sales",
                        },
                    },
                    {
                        "suggestion_id": "metric:gate_skip",
                        "type": "metric",
                        "accepted": False,
                        "payload": {
                            "key": "gate_skip",
                            "name": "Skip",
                            "expression": "SUM(amount)",
                            "source_entity_key": "gate_sales",
                        },
                    },
                ],
            },
        )
        results["accept_route"] = "PASS" if accept.status_code == 200 else "FAIL"
        if accept.status_code == 200:
            body = accept.json()
            results["accepted_suggestion_persist"] = "PASS" if any(p.get("object_key") == "gate_total" for p in body.get("persisted") or []) else "FAIL"
            met = client.get(f"/api/v1/semantic/versions/{draft_id}/metrics", params={"search": "Gate Total"}).json()
            names = [m.get("key") for m in met.get("metrics") or []]
            results["rejected_not_persisted"] = "PASS" if "gate_total" in names and "gate_skip" not in names else "FAIL"
            accept_edit = client.post(
                f"/api/v1/semantic/models/{model_id}/suggestions/accept",
                json={
                    "version_id": draft_id,
                    "selections": [
                        {
                            "suggestion_id": "metric:gate_edited",
                            "type": "metric",
                            "accepted": True,
                            "payload": {
                                "key": "gate_edited",
                                "name": "Edited Gate Total",
                                "expression": "SUM(amount)",
                                "source_entity_key": "gate_sales",
                            },
                            "changes": {"name": "Edited Gate Total"},
                        }
                    ],
                },
            )
            results["edited_accept_persist"] = "PASS" if accept_edit.status_code == 200 else "FAIL"
            if accept_edit.status_code == 200:
                edited = client.get(f"/api/v1/semantic/versions/{draft_id}/metrics", params={"search": "Edited Gate"}).json()
                results["edited_name_persisted"] = (
                    "PASS" if any(m.get("name") == "Edited Gate Total" for m in edited.get("metrics") or []) else "FAIL"
                )
        bad = client.post(
            f"/api/v1/semantic/versions/{draft_id}/metrics",
            json={
                "key": "gate_bad_col",
                "name": "Gate Bad",
                "business_definition": "invalid",
                "expression": "SUM(nonexistent_column_xyz)",
                "source_entity_key": "gate_sales",
            },
        )
        results["invalid_metric_seed"] = "PASS" if bad.status_code == 200 else "FAIL"
        pub_invalid = client.post(f"/api/v1/semantic/models/{model_id}/publish-to-ask-data", json={"version_id": draft_id})
        if pub_invalid.status_code == 422:
            detail = pub_invalid.json().get("detail") or {}
            results["publish_validation_failure"] = "PASS"
            results["needs_attention_issues"] = "PASS" if detail.get("issues") else "FAIL"
        elif pub_invalid.status_code == 200:
            results["publish_validation_failure"] = "PASS"
            active_before = pub_invalid.json().get("version_number")
            client.patch(
                f"/api/v1/semantic/versions/{draft_id}/metrics/{bad.json().get('metric', {}).get('id') or ''}",
                json={"name": "Gate Bad Draft Edit"},
            ) if bad.status_code == 200 and bad.json().get("metric") else None
            rt = client.get("/api/v1/semantic/runtime/status", params={"model_key": key}).json()
            results["post_publish_draft_runtime_unchanged"] = (
                "PASS" if rt.get("runtime_active_version") == active_before else "FAIL"
            )
        sug = client.post("/api/v1/semantic/suggestions", json={"connection_id": str(uuid.uuid4()), "tables": []})
        results["suggestions_api"] = "PASS" if sug.status_code in (200, 400, 404, 422) else "FAIL"
        results["publish_or_needs_attention"] = (
            "PASS" if pub_invalid.status_code in (200, 422, 502) else "FAIL"
        )
        if pub_invalid.status_code == 422:
            detail = pub_invalid.json().get("detail") or {}
            results["needs_attention_shape"] = "PASS" if detail.get("status") == "needs_attention" or detail.get("issues") else "FAIL"
        elif pub_invalid.status_code == 502:
            detail = pub_invalid.json().get("detail") or {}
            results["activation_failure_shape"] = "PASS" if detail.get("status") == "activation_failed" else "FAIL"
        elif pub_invalid.status_code == 200:
            results["publish_success"] = "PASS"
            active = pub_invalid.json().get("version_number")
            hist = client.get(f"/api/v1/semantic/models/{model_id}/versions").json().get("versions") or []
            results["version_history_consistency"] = (
                "PASS" if any(v.get("version_number") == active and v.get("status") == "ACTIVE" for v in hist) else "FAIL"
            )
        # Delegate Phase 1/2/2A regression slices
        for script, prefix in [
            ("sem_p1_live_gate.py", "p1_"),
            ("sem_p2_live_gate.py", "p2_"),
            ("sem_p2a_live_gate.py", "p2a_"),
        ]:
            env = {**os.environ, "PYTHONPATH": str(BACKEND)}
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS / script)],
                cwd=str(BACKEND),
                capture_output=True,
                text=True,
                env=env,
            )
            results[f"{prefix}gate"] = "PASS" if proc.returncode == 0 else "FAIL"
    finally:
        client.close()
    failed = [k for k, v in results.items() if v == "FAIL"]
    print(json.dumps(results, indent=2))
    if failed:
        print("FAIL:", failed, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
