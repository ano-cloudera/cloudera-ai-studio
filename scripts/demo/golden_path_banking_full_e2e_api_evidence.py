#!/usr/bin/env python3
"""Golden Banking full E2E API evidence (live CAI sim + phase chat scripts)."""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "demo"))

from golden_banking_knowledge_constants import LIBRARY_NAME, PDF_SEGMENT, PDF_TRANSACTION  # noqa: E402
from golden_banking_semantic_constants import MODEL_KEY, MODEL_NAME, REQUIRED_METRIC_KEYS  # noqa: E402
from golden_e2e_common import (  # noqa: E402
    EVIDENCE,
    GOLDEN_PROMPT_KEY,
    GOLDEN_PROMPT_NAME,
    GOLDEN_SKILL_KEY,
    GOLDEN_SKILL_NAME,
    PHASE1_EVID,
    PHASE2_EVID,
    PHASE3_EVID,
    backend_ready,
    http,
    load_json,
    metadata_snapshot,
    qdrant_ready,
    run_script,
)

OUT = EVIDENCE / "api-e2e-evidence.json"


def _ensure_golden_prompt() -> dict:
    st, listed = http("GET", "/api/v1/prompts")
    existing = None
    if st == 200 and isinstance(listed, dict):
        for row in listed.get("prompts") or []:
            if row.get("key") == GOLDEN_PROMPT_KEY:
                existing = row
                break
    if existing:
        return {"action": "reuse", "prompt_id": existing["id"], "key": GOLDEN_PROMPT_KEY}
    body = {
        "name": GOLDEN_PROMPT_NAME,
        "key": GOLDEN_PROMPT_KEY,
        "scope": "project",
        "description": "Summarize structured banking analytical results concisely (Golden E2E).",
        "initial_content": "You summarize banking KPIs clearly for executives. Use only supplied metrics.",
    }
    st, created = http("POST", "/api/v1/prompts", body)
    if st != 200:
        return {"ok": False, "error": created}
    prompt_id = created["prompt"]["id"]
    http(
        "POST",
        f"/api/v1/prompts/{prompt_id}/versions",
        {"content": body["initial_content"] + "\n\nFocus on totals, trends, and caveats."},
    )
    return {"action": "created", "prompt_id": prompt_id, "key": GOLDEN_PROMPT_KEY}


def _ensure_golden_skill(prompt_key: str) -> dict:
    st, listed = http("GET", "/api/v1/skills")
    existing = None
    if st == 200 and isinstance(listed, dict):
        for row in listed.get("skills") or []:
            if row.get("key") == GOLDEN_SKILL_KEY:
                existing = row
                break
    if existing:
        skill_id = existing["id"]
        st, versions = http("GET", f"/api/v1/skills/{skill_id}/versions")
        if st == 200 and isinstance(versions, dict) and versions.get("versions"):
            vid = versions["versions"][-1]["id"]
            http("POST", f"/api/v1/skills/{skill_id}/versions/{vid}/publish")
    else:
        st, created = http(
            "POST",
            "/api/v1/skills",
            {
                "name": GOLDEN_SKILL_NAME,
                "key": GOLDEN_SKILL_KEY,
                "scope": "project",
                "description": "Golden Banking demo analyst skill (existing contracts only).",
                "instructions": "Answer banking questions using governed metrics when available.",
                "prompt_key": prompt_key,
                "allowed_tools": [],
                "config": {},
            },
        )
        if st != 200:
            return {"ok": False, "error": created}
        skill_id = created["skill"]["id"]
    st, versions = http("GET", f"/api/v1/skills/{skill_id}/versions")
    version_id = None
    if st == 200 and isinstance(versions, dict) and versions.get("versions"):
        version_id = versions["versions"][-1]["id"]
        http("POST", f"/api/v1/skills/{skill_id}/versions/{version_id}/publish")
    exec_result = None
    if version_id:
        st, exec_result = http(
            "POST",
            f"/api/v1/skills/{skill_id}/execute",
            {"input": "Summarize total transaction exposure for Golden E2E validation."},
        )
    return {
        "skill_id": skill_id,
        "execute_status": st if version_id else None,
        "execute_ok": st == 200 if version_id else False,
        "execute_body": exec_result if isinstance(exec_result, dict) else str(exec_result)[:300],
    }


def _ai_registry_check() -> dict:
    st_p, providers = http("GET", "/api/v1/ai/providers")
    st_m, models = http("GET", "/api/v1/ai/models")
    st_a, assignments = http("GET", "/api/v1/ai/assignments")
    secrets_ok = True
    if st_p == 200 and isinstance(providers, dict):
        for row in providers.get("providers") or []:
            ref = row.get("secret_ref") or ""
            if ref and not ref.startswith("env://"):
                secrets_ok = False
            if row.get("secret_value"):
                secrets_ok = False
    return {
        "providers_ok": st_p == 200,
        "models_ok": st_m == 200,
        "assignments_ok": st_a == 200,
        "secret_refs_env_style": secrets_ok,
        "provider_count": len(providers.get("providers") or []) if isinstance(providers, dict) else 0,
        "model_count": len(models.get("models") or []) if isinstance(models, dict) else 0,
    }


def _usage_check() -> dict:
    st, events = http("GET", "/usage/events?days=7&limit=20")
    st2, summary = http("GET", "/usage/summary?days=7")
    count = len(events.get("events") or []) if st == 200 and isinstance(events, dict) else 0
    return {"events_http": st, "summary_http": st2, "recent_events": count}


def _semantic_surface(model_id: str) -> dict:
    st, detail = http("GET", f"/api/v1/semantic/models/{model_id}")
    metrics = []
    dims = []
    if st == 200 and isinstance(detail, dict):
        version_id = (detail.get("model") or {}).get("draft_version_id") or (detail.get("model") or {}).get(
            "active_version_id"
        )
        if version_id:
            m_st, m_body = http("GET", f"/api/v1/semantic/versions/{version_id}/metrics")
            d_st, d_body = http("GET", f"/api/v1/semantic/versions/{version_id}/dimensions")
            metrics = [m.get("key") for m in (m_body.get("metrics") or []) if isinstance(m_body, dict)]
            dims = [d.get("key") for d in (d_body.get("dimensions") or []) if isinstance(d_body, dict)]
    rt_st, rt = http("GET", f"/api/v1/semantic/runtime/status?model_key={MODEL_KEY}")
    return {
        "model_visible": st == 200,
        "required_metrics_present": all(k in metrics for k in REQUIRED_METRIC_KEYS),
        "runtime_ok": rt_st == 200 and isinstance(rt, dict) and rt.get("runtime_status") in {"healthy", "degraded"},
        "runtime": rt if rt_st == 200 else None,
    }


def _knowledge_surface(library_id: str) -> dict:
    st, docs = http("GET", f"/api/v1/libraries/{library_id}/documents?page=1&page_size=20")
    names = []
    ready = False
    if st == 200 and isinstance(docs, dict):
        for row in docs.get("items") or []:
            names.append(row.get("original_filename") or row.get("filename"))
        ready = all(row.get("status") == "READY" for row in docs.get("items") or []) and len(names) >= 2
    return {
        "documents": names,
        "both_pdfs": PDF_TRANSACTION.name in names and PDF_SEGMENT.name in names,
        "all_ready": ready,
    }


def _chat_scripts() -> dict:
    rows = {}
    for label, script in (
        ("phase1_raw", "phase1_api_ask_evidence.py"),
        ("phase2_rag", "phase2_api_rag_evidence.py"),
        ("phase3_governed", "phase3_chat_governed_evidence.py"),
    ):
        code, detail = run_script(script, timeout=300.0)
        rows[label] = {"code": code, "detail": detail}
    p1 = load_json(PHASE1_EVID / "api-ask-responses.json") or {}
    p2 = load_json(PHASE2_EVID / "api-rag-evidence.json") or {}
    p3 = load_json(PHASE3_EVID / "chat-governed-evidence.json") or {}
    raw_modes = [s.get("context_mode") for s in (p1.get("scenarios") or []) if isinstance(s, dict)]
    return {
        "scripts": rows,
        "raw_indicator": p1.get("all_success") is True and all(m == "RAW_TABLE" for m in raw_modes if m),
        "knowledge_mode": (p2.get("routing") or {}).get("knowledge_mode") == "rag",
        "governed_mode": (p3.get("scenarios") or {}).get("total_amount", {}).get("context_mode") == "GOVERNED_SEMANTIC",
        "retrieval_ok": p2.get("retrieval_ok") is True,
        "contrast_ok": p2.get("contrast_ok") is True,
        "governed_all_ok": p3.get("all_ok") is True,
    }


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if not backend_ready():
        print("backend not ready", file=sys.stderr)
        return 1

    env_state = {
        "backend_ready": True,
        "qdrant_ready": qdrant_ready(),
        "metadata_snapshot": metadata_snapshot(),
        "worker_hint": os.environ.get("UVICORN_WORKERS", "1"),
    }

    conn = load_json(PHASE1_EVID / "connector-registration.json") or {}
    lib = load_json(PHASE2_EVID / "library-registration.json") or {}
    sem = load_json(PHASE3_EVID / "semantic-registration.json") or {}
    connector_id = conn.get("connector_id")
    library_id = lib.get("library_id")
    model_id = sem.get("model_id")

    datasource = {"ok": False}
    if connector_id:
        test_st, test_body = http("POST", f"/api/v1/connectors/{connector_id}/test")
        tbl_st, tbl_body = http("GET", f"/api/v1/connectors/{connector_id}/tables?schema=banking_demo")
        names = {t.get("name") for t in (tbl_body.get("tables") or []) if isinstance(tbl_body, dict)}
        datasource = {
            "connector_id": connector_id,
            "connection_test": test_st == 200 and isinstance(test_body, dict) and test_body.get("status") == "SUCCESS",
            "customers_table": "customers" in names,
            "transactions_table": "transactions" in names,
        }
        datasource["ok"] = all(
            datasource[k] for k in ("connection_test", "customers_table", "transactions_table")
        )

    session_id = f"golden-e2e-{uuid.uuid4().hex[:10]}"
    chat_flow = _chat_scripts()
    chat_flow["session_id"] = session_id

    prompt = _ensure_golden_prompt()
    skill = _ensure_golden_skill(GOLDEN_PROMPT_KEY)
    ai = _ai_registry_check()
    usage = _usage_check()

    knowledge = _knowledge_surface(library_id) if library_id else {"ok": False}
    knowledge["library_name"] = LIBRARY_NAME
    semantic = _semantic_surface(model_id) if model_id else {"ok": False}
    semantic["model_name"] = MODEL_NAME

    payload = {
        "environment": env_state,
        "data_source": datasource,
        "knowledge": knowledge,
        "semantic": semantic,
        "chat": chat_flow,
        "prompt": prompt,
        "skill": skill,
        "chat_skill_limitation": "Chat UI does not invoke skills directly; validated via /api/v1/skills/{id}/execute.",
        "ai_registry": ai,
        "usage": usage,
    }
    payload["ok"] = (
        datasource.get("ok")
        and knowledge.get("all_ready")
        and semantic.get("runtime_ok")
        and chat_flow.get("governed_all_ok")
        and chat_flow.get("retrieval_ok")
        and ai.get("providers_ok")
        and skill.get("execute_ok", True)
    )
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": payload["ok"], "path": str(OUT)}, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
