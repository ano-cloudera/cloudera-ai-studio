#!/usr/bin/env python3
"""M7D live API gate (registry paths mirroring Settings UI)."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid

BASE = os.environ.get("M7D_BASE_URL", "http://127.0.0.1:8001")
MODEL_ID = os.environ.get("M7D_GEMINI_MODEL_ID", "e030608f-ffa6-4662-989d-29137eee83f0")
RAG_LIB = os.environ.get("M7D_RAG_LIBRARY_ID", "0404030d-ab3e-44ae-b90c-713539cd0a11")
RAG_QUERY = os.environ.get(
    "M7D_RAG_QUERY",
    "What is the maximum travel reimbursement?",
)
ASK_Q = "What is total sales by month?"


def req(method: str, path: str, body: dict | None = None) -> tuple[int, dict | str]:
    data = None if body is None else json.dumps(body).encode()
    r = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def main() -> None:
    results: dict[str, str] = {}
    sid = f"m7d-{uuid.uuid4().hex[:8]}"

    # Assign ASK_DATA
    st, _ = req("PUT", "/api/v1/ai/assignments/ASK_DATA", {"model_id": MODEL_ID})
    results["assign_ask_data"] = "PASS" if st == 200 else f"FAIL http={st}"

    st, chat = req(
        "POST",
        "/chat",
        {
            "session_id": sid,
            "question": ASK_Q,
            "provider": "gemini",
            "model": "gemini-3.8-flash",
            "mode": "ask_data",
        },
    )
    mr = chat.get("model_resolution") if isinstance(chat, dict) else None
    results["ask_data_registry"] = (
        "PASS"
        if st == 200 and isinstance(mr, dict) and mr.get("assignment_source") == "PROJECT"
        else f"FAIL st={st} mr={mr}"
    )

    time.sleep(11)
    results["ask_data_idle_wait"] = "PASS"

    st2, chat2 = req(
        "POST",
        "/chat",
        {
            "session_id": sid,
            "question": "What is total revenue?",
            "provider": "gemini",
            "model": "gemini-3.8-flash",
            "mode": "ask_data",
        },
    )
    results["ask_data_second_manual"] = "PASS" if st2 == 200 else f"FAIL st={st2}"

    st, _ = req("DELETE", "/api/v1/ai/assignments/ASK_DATA")
    st, chat3 = req(
        "POST",
        "/chat",
        {
            "session_id": sid + "-legacy",
            "question": ASK_Q,
            "provider": "gemini",
            "model": "gemini-3.8-flash",
            "mode": "ask_data",
        },
    )
    mr3 = chat3.get("model_resolution") if isinstance(chat3, dict) else "n/a"
    results["ask_data_legacy"] = "PASS" if st == 200 and mr3 is None else f"FAIL st={st} mr={mr3}"

    # RAG registry
    st, _ = req("PUT", "/api/v1/ai/assignments/RAG_GENERATION", {"model_id": MODEL_ID})
    st, rag = req(
        "POST",
        "/api/v1/rag/query",
        {
            "query": RAG_QUERY,
            "provider": "gemini",
            "model": "gemini-3.8-flash",
            "library_ids": [RAG_LIB],
        },
    )
    cites = rag.get("citations") if isinstance(rag, dict) else None
    results["rag_registry"] = (
        "PASS"
        if st == 200 and isinstance(rag, dict) and str(rag.get("status", "")).lower() in ("ok", "success", "completed")
        else f"FAIL st={st} body={str(rag)[:200]}"
    )
    results["rag_citations"] = "PASS" if cites is not None else "FAIL no citations key"

    st, _ = req("DELETE", "/api/v1/ai/assignments/RAG_GENERATION")
    st, rag2 = req(
        "POST",
        "/api/v1/rag/query",
        {
            "query": RAG_QUERY,
            "provider": "gemini",
            "model": "gemini-3.8-flash",
            "library_ids": [RAG_LIB],
        },
    )
    results["rag_legacy"] = "PASS" if st == 200 else f"FAIL st={st}"

    # Skills - resolve skill id
    st, skills_body = req("GET", "/api/v1/skills")
    skill_id = None
    if isinstance(skills_body, dict):
        for s in skills_body.get("skills", []):
            if "m7b" in s.get("key", "").lower() or s.get("key") == "prompt_only_demo":
                skill_id = s["id"]
                break
        if not skill_id and skills_body.get("skills"):
            skill_id = skills_body["skills"][0]["id"]

    st, _ = req("PUT", "/api/v1/ai/assignments/SKILLS", {"model_id": MODEL_ID})
    if skill_id:
        st, sk = req("POST", f"/api/v1/skills/{skill_id}/execute", {"input": "M7D validation"})
        results["skills_registry"] = "PASS" if st == 200 else f"FAIL st={st} {str(sk)[:180]}"
    else:
        results["skills_registry"] = "FAIL no skill"

    st, _ = req("DELETE", "/api/v1/ai/assignments/SKILLS")
    if skill_id:
        st, sk2 = req("POST", f"/api/v1/skills/{skill_id}/execute", {"input": "M7D validation"})
        results["skills_legacy"] = "PASS" if st == 200 else f"FAIL st={st}"

    # Broken assignment: disable model
    st, _ = req("PUT", "/api/v1/ai/assignments/ASK_DATA", {"model_id": MODEL_ID})
    st, _ = req("PATCH", f"/api/v1/ai/models/{MODEL_ID}", {"enabled": False})
    st, broken = req(
        "POST",
        "/chat",
        {
            "session_id": sid + "-broken",
            "question": ASK_Q,
            "provider": "gemini",
            "model": "gemini-3.8-flash",
            "mode": "ask_data",
        },
    )
    ans = broken.get("answer") if isinstance(broken, dict) else None
    caveats = ans.get("caveats", []) if isinstance(ans, dict) else []
    broken_ok = isinstance(broken, dict) and broken.get("status") == "ERROR" and any(
        "MODEL_DISABLED" in str(c) for c in caveats
    )
    results["broken_model_disabled"] = "PASS" if broken_ok else f"FAIL st={st} body={str(broken)[:120]}"
    req("PATCH", f"/api/v1/ai/models/{MODEL_ID}", {"enabled": True})
    req("DELETE", "/api/v1/ai/assignments/ASK_DATA")

    # Delete protection (temp model on temp provider if possible - use existing model assigned)
    st, _ = req("PUT", "/api/v1/ai/assignments/ASK_DATA", {"model_id": MODEL_ID})
    st, delm = req("DELETE", f"/api/v1/ai/models/{MODEL_ID}")
    results["model_delete_in_use"] = "PASS" if st == 409 else f"FAIL st={st} detail={delm}"
    req("DELETE", "/api/v1/ai/assignments/ASK_DATA")

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
