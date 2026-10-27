#!/usr/bin/env python3
"""M7D.1 UI-equivalent API flows (Knowledge, Prompts, Skills, Semantic, Connector→Semantic)."""
from __future__ import annotations

import json
import os
import tempfile
import time
import urllib.error
import urllib.request
import uuid

BASE = os.environ.get("M7D_BASE_URL", "http://127.0.0.1:8001")


def req(method: str, path: str, body: dict | None = None, data: bytes | None = None, headers: dict | None = None) -> tuple[int, dict | str]:
    h = dict(headers or {})
    payload = data
    if body is not None:
        payload = json.dumps(body).encode()
        h.setdefault("Content-Type", "application/json")
    r = urllib.request.Request(BASE + path, data=payload, method=method, headers=h)
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


def knowledge_flow() -> dict:
    name = f"M7D-Knowledge-{uuid.uuid4().hex[:6]}"
    st, lib = req("POST", "/api/v1/libraries", {"name": name})
    if st != 200:
        return {"pass": False, "step": "create_library", "st": st, "body": lib}
    lib_id = lib["library"]["id"]
    content = b"M7D validation document. Maximum travel reimbursement is 7500 USD for closure tests.\n"
    boundary = f"----m7d{uuid.uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="m7d.txt"\r\n'
        f"Content-Type: text/plain\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    st, doc_resp = req(
        "POST",
        f"/api/v1/libraries/{lib_id}/documents",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    if st != 200:
        req("DELETE", f"/api/v1/libraries/{lib_id}")
        return {"pass": False, "step": "upload", "st": st}
    doc_id = doc_resp["document"]["id"]
    ready = False
    for _ in range(30):
        st, docs = req("GET", f"/api/v1/libraries/{lib_id}/documents")
        d = next(x for x in docs["documents"] if x["id"] == doc_id)
        if d.get("status") == "READY":
            ready = True
            break
        if d.get("status") == "FAILED":
            break
        time.sleep(2)
    req("DELETE", f"/api/v1/libraries/{lib_id}/documents/{doc_id}")
    req("DELETE", f"/api/v1/libraries/{lib_id}")
    return {"pass": ready, "library_id": lib_id, "document_id": doc_id, "status": d.get("status") if not ready else "READY"}


def prompts_flow() -> dict:
    key = f"m7d.validation.{uuid.uuid4().hex[:8]}"
    st, created = req(
        "POST",
        "/api/v1/prompts",
        {"name": "M7D Validation Prompt", "key": key, "scope": "project", "initial_content": "M7D v1"},
    )
    if st != 200:
        return {"pass": False, "step": "create", "st": st}
    pid = created["prompt"]["id"]
    vid = req("GET", f"/api/v1/prompts/{pid}/versions")[1]["versions"][0]["id"]
    req("POST", f"/api/v1/prompts/{pid}/versions/{vid}/publish")
    resolved = req("POST", "/api/v1/prompts/resolve", {"prompt_key": key})[1]
    req("DELETE", f"/api/v1/prompts/{pid}")
    return {"pass": resolved.get("content") == "M7D v1", "key": key}


def skills_flow() -> dict:
    key = f"m7d.validation.skill.{uuid.uuid4().hex[:8]}"
    st, sk = req(
        "POST",
        "/api/v1/skills",
        {
            "name": "M7D Skill",
            "key": key,
            "scope": "workspace",
            "instructions": "Reply with exactly: validated",
            "allowed_tools": [],
            "config": {"handler_type": "prompt_only"},
        },
    )
    if st != 200:
        return {"pass": False, "st": st}
    sid = sk["skill"]["id"]
    vid = req("GET", f"/api/v1/skills/{sid}/versions")[1]["versions"][0]["id"]
    req("POST", f"/api/v1/skills/{sid}/versions/{vid}/publish")
    ex = req("POST", f"/api/v1/skills/{sid}/execute", {"input": "test"})
    req("DELETE", f"/api/v1/skills/{sid}")
    return {"pass": ex[0] == 200, "skill_id": sid}


def connector_semantic_flow() -> dict:
    connectors = req("GET", "/api/v1/connectors")[1]["connectors"]
    pg = next(c for c in connectors if c.get("connector_type") == "postgres" and c.get("enabled"))
    cid = pg["id"]
    st, test = req("POST", f"/api/v1/connectors/{cid}/test")
    if st != 200 or test.get("status") != "SUCCESS":
        return {"pass": False, "step": "connector_test", "test": test}
    models = req("GET", "/api/v1/semantic/models")[1]["models"]
    if not models:
        st, sm = req("POST", "/api/v1/semantic/models", {"name": "M7D Semantic", "key": f"m7d_sem_{uuid.uuid4().hex[:6]}"})
        mid = sm["model"]["id"]
    else:
        mid = models[0]["id"]
    versions = req("GET", f"/api/v1/semantic/models/{mid}/versions")[1]["versions"]
    draft = next((v for v in versions if v.get("status") == "DRAFT"), None)
    if not draft:
        st, nv = req("POST", f"/api/v1/semantic/models/{mid}/versions", {})
        vid = nv["version"]["id"]
    else:
        vid = draft["id"]
    meta = req("GET", f"/api/v1/connectors/{cid}/tables?schema=public&limit=5")
    if meta[0] != 200:
        return {"pass": False, "step": "list_tables", "code": meta[0], "body": meta[1]}
    tables = meta[1].get("tables") or []
    if not tables:
        return {"pass": False, "step": "no_tables"}
    schema = tables[0].get("schema") or "public"
    table = None
    for candidate in tables:
        name = candidate.get("name") or candidate.get("table_name")
        if name and name != "customers":
            table = name
            break
    if not table:
        table = tables[0].get("name") or tables[0].get("table_name")
    preview = req(
        "POST",
        f"/api/v1/semantic/versions/{vid}/entities/import-preview",
        {
            "connector_id": cid,
            "catalog": "",
            "schema": schema,
            "table": table,
        },
    )
    if preview[0] != 200:
        return {"pass": False, "step": "import_preview", "code": preview[0]}
    imp = req(
        "POST",
        f"/api/v1/semantic/versions/{vid}/entities/import",
        {
            "connector_id": cid,
            "catalog": "",
            "schema": schema,
            "table": table,
            "name": f"M7D {table}",
            "key": f"m7d_{table}_{uuid.uuid4().hex[:4]}",
            "dimension_columns": [],
        },
    )
    return {
        "pass": imp[0] == 200,
        "connector_id": cid,
        "semantic_model_id": mid,
        "version_id": vid,
        "table": table,
        "entity": imp[1] if imp[0] == 200 else imp,
    }


def semantic_lifecycle_flow() -> dict:
    models = req("GET", "/api/v1/semantic/models")[1]["models"]
    if not models:
        return {"pass": False, "reason": "no_semantic_models"}
    mid = models[0]["id"]
    versions = req("GET", f"/api/v1/semantic/models/{mid}/versions")[1]["versions"]
    draft = next((v for v in versions if v.get("status") == "DRAFT"), versions[0] if versions else None)
    if not draft:
        return {"pass": False, "reason": "no_version"}
    vid = draft["id"]
    val = req("POST", f"/api/v1/semantic/versions/{vid}/validate")
    pub = None
    if draft.get("status") == "DRAFT":
        pub = req("POST", f"/api/v1/semantic/versions/{vid}/publish")
    deployments = req("GET", "/api/v1/semantic/runtime/deployments")
    return {
        "pass": val[0] == 200,
        "model_id": mid,
        "version_id": vid,
        "validate": val[0],
        "publish": pub[0] if pub else None,
        "deployments": deployments[0],
    }


def main() -> None:
    results = {
        "knowledge": knowledge_flow(),
        "prompts": prompts_flow(),
        "skills": skills_flow(),
        "connector_semantic": connector_semantic_flow(),
        "semantic_lifecycle": semantic_lifecycle_flow(),
    }
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
