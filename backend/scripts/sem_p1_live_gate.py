#!/usr/bin/env python3
"""Live API gates for SEMANTIC_LAYER_V2 Phase 1."""
from __future__ import annotations

import json
import sys
import uuid

import httpx

from app.core.config import get_settings

BASE = "http://127.0.0.1:8001"


def main() -> int:
    results: dict[str, str] = {}
    client = httpx.Client(base_url=BASE, timeout=120.0)
    try:
        results["health"] = "PASS" if client.get("/health").status_code == 200 else "FAIL"
        results["ready"] = "PASS" if client.get("/health/ready").status_code == 200 else "FAIL"
        opts = client.get("/api/v1/chat/context-options", params={"limit": 50})
        results["context_options"] = "PASS" if opts.status_code == 200 else "FAIL"
        groups = opts.json().get("groups") or [] if opts.status_code == 200 else []
        ids = {g.get("id") for g in groups}
        results["context_groups"] = "PASS" if {"data", "semantic", "knowledge"}.issubset(ids) else "FAIL"
        data_opts = next((g.get("options") or [] for g in groups if g.get("id") == "data"), [])
        results["data_has_table"] = "PASS" if any(o.get("type") == "table" for o in data_opts) else "FAIL"
        table_id = next((o.get("id") for o in data_opts if o.get("type") == "table"), None)
        semantic_opts = next((g.get("options") or [] for g in groups if g.get("id") == "semantic"), [])
        results["semantic_picker"] = "PASS" if semantic_opts else "FAIL"
        default_key = get_settings().semantic_default_model_key
        model_id = next(
            (
                o.get("id")
                for o in semantic_opts
                if o.get("type") == "semantic_model"
                and (o.get("metadata") or {}).get("model_key") == default_key
            ),
            None,
        )
        if not model_id:
            model_id = next(
                (
                    o.get("id")
                    for o in semantic_opts
                    if o.get("type") == "semantic_model" and (o.get("subtitle") or "").lower() == "published"
                ),
                None,
            )
        if not model_id:
            model_id = next((o.get("id") for o in semantic_opts if o.get("type") == "semantic_model"), None)
        metric_id = None
        if model_id:
            metric_id = next(
                (
                    o.get("id")
                    for o in semantic_opts
                    if o.get("type") == "semantic_metric"
                    and (o.get("metadata") or {}).get("model_id") == model_id
                ),
                None,
            )
        knowledge_opts = next((g.get("options") or [] for g in groups if g.get("id") == "knowledge"), [])
        results["knowledge_picker"] = "PASS" if knowledge_opts is not None else "FAIL"

        ask_payload = {
            "session_id": f"sem-p1-{uuid.uuid4()}",
            "question": "What is total sales by month?",
            "provider": "gemini",
            "model": "gemini-3.8-flash",
        }
        if table_id:
            ask_payload["context_sources"] = [{"type": "table", "id": table_id, "name": "raw table"}]
            raw = client.post("/chat", json=ask_payload)
            if raw.status_code == 200:
                body = raw.json()
                results["raw_table_ask"] = "PASS" if body.get("context_mode") == "RAW_TABLE" else "FAIL"
                results["raw_table_status"] = "PASS" if body.get("status") in {"SUCCESS", "NO_DATA", "CLARIFICATION"} else "FAIL"
            else:
                results["raw_table_ask"] = f"FAIL HTTP {raw.status_code}"
        else:
            results["raw_table_ask"] = "SKIP no table"

        if metric_id:
            metric_name = next(
                (o.get("name") for o in semantic_opts if o.get("id") == metric_id),
                "metric",
            )
            m_payload = {
                **ask_payload,
                "session_id": f"sem-p1-m-{uuid.uuid4()}",
                "question": f"What is {metric_name} by month?",
                "context_sources": [{"type": "semantic_metric", "id": metric_id, "name": metric_name}],
            }
            gov = client.post("/chat", json=m_payload)
            if gov.status_code == 200:
                body = gov.json()
                results["metric_ask"] = (
                    "PASS"
                    if body.get("context_mode") == "GOVERNED_SEMANTIC"
                    and body.get("status") in {"SUCCESS", "NO_DATA", "CLARIFICATION", "clarification_required"}
                    else "FAIL"
                )
                if results["metric_ask"] == "FAIL":
                    results["metric_ask_debug"] = {
                        "status": body.get("status"),
                        "context_mode": body.get("context_mode"),
                        "strategy": body.get("strategy"),
                        "caveats": (body.get("answer") or {}).get("caveats"),
                    }
            else:
                results["metric_ask"] = f"FAIL HTTP {gov.status_code}"
        else:
            results["metric_ask"] = "SKIP no metric"

        if model_id:
            sm_payload = {
                **ask_payload,
                "session_id": f"sem-p1-sm-{uuid.uuid4()}",
                "question": "What is total sales this month?",
                "context_sources": [{"type": "semantic_model", "id": model_id, "name": "model"}],
            }
            sm = client.post("/chat", json=sm_payload)
            results["semantic_model_ask"] = "PASS" if sm.status_code == 200 else f"FAIL HTTP {sm.status_code}"
        else:
            results["semantic_model_ask"] = "SKIP"

        amb = client.post(
            "/chat",
            json={
                "session_id": f"sem-p1-amb-{uuid.uuid4()}",
                "question": "compare sales_sell_in and sales_sell_out by month",
                "provider": "gemini",
                "model": "gemini-3.8-flash",
            },
        )
        if amb.status_code == 200:
            body = amb.json()
            results["ambiguous_clarification"] = (
                "PASS" if body.get("status") == "clarification_required" and body.get("clarification") else "FAIL"
            )
            opts_ok = body.get("clarification", {}).get("options") if isinstance(body.get("clarification"), dict) else None
            results["clarification_structured"] = "PASS" if opts_ok else "FAIL"
        else:
            results["ambiguous_clarification"] = f"FAIL HTTP {amb.status_code}"

        bogus = client.post(
            "/chat",
            json={
                **ask_payload,
                "session_id": f"sem-p1-xproj-{uuid.uuid4()}",
                "context_sources": [{"type": "table", "id": encode_bogus_table_id(), "name": "x"}],
            },
        )
        results["cross_project_table"] = "PASS" if bogus.status_code == 200 and bogus.json().get("status") == "ERROR" else "FAIL"

        write_block = client.post(
            "/chat",
            json={
                **ask_payload,
                "session_id": f"sem-p1-write-{uuid.uuid4()}",
                "question": "DELETE FROM public.sales",
                "context_sources": ask_payload.get("context_sources"),
            },
        )
        if write_block.status_code == 200:
            st = write_block.json().get("status")
            results["write_blocked"] = "PASS" if st in {"ERROR", "CLARIFICATION", "UNSUPPORTED"} else "FAIL"
        else:
            results["write_blocked"] = "PASS"

        print(json.dumps(results, indent=2))
        failed = [k for k, v in results.items() if str(v).startswith("FAIL")]
        return 0 if not failed else 1
    finally:
        client.close()


def encode_bogus_table_id() -> str:
    from app.ask_data.table_context_id import encode_raw_table_id

    return encode_raw_table_id(
        connector_id=uuid.uuid4(),
        catalog=None,
        schema="public",
        table="other_project_sales",
    )


if __name__ == "__main__":
    sys.path.insert(0, ".")
    raise SystemExit(main())
