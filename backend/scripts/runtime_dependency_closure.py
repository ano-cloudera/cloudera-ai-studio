#!/usr/bin/env python3
"""Live runtime dependency closure checks (Postgres datasource, RAG, Semantic, Ask Data).

Requires backend on BASE_URL (default http://127.0.0.1:8001) with:
- STATE_STORE=postgres + DATABASE_URL (platform)
- DEMO_POSTGRES_PASSWORD + demo_sales DB (scripts/demo/seed_demo_sales_db.sh)
- QDRANT_URL for RAG checks
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
import urllib.error
import urllib.request
from typing import Any

BASE = os.environ.get("CLOSURE_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
RESULTS: dict[str, str] = {}


def req(method: str, path: str, data: Any | None = None, timeout: float = 120.0) -> tuple[int, Any]:
    url = f"{BASE}{path}"
    body = None
    headers = {"Accept": "application/json"}
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed


def multipart_upload(library_id: str, filename: str, content: bytes) -> tuple[int, Any]:
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: text/plain\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    url = f"{BASE}/api/v1/libraries/{library_id}/documents"
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as resp:
        return resp.status, json.loads(resp.read().decode())


def ensure_demo_connector() -> str:
    host = os.environ.get("DEV_POSTGRES_HOST", "127.0.0.1")
    port = int(os.environ.get("DEV_POSTGRES_PORT", "55432"))
    database = os.environ.get("DEV_POSTGRES_DATABASE", "demo_sales")
    user = os.environ.get("DEV_POSTGRES_USER", "demo_sales")
    key = "demo_sales_live"
    code, listed = req("GET", "/api/v1/connectors")
    assert code == 200, listed
    for c in listed.get("connectors", []):
        if c.get("key") == key:
            return c["id"]
    if not os.environ.get("DEMO_POSTGRES_PASSWORD"):
        raise RuntimeError("DEMO_POSTGRES_PASSWORD not set")
    code, created = req(
        "POST",
        "/api/v1/connectors",
        {
            "name": "Demo Sales PostgreSQL",
            "key": key,
            "connector_type": "postgres",
            "config": {"host": host, "port": port, "database": database, "username": user, "sslmode": "prefer"},
            "secret_ref": "env://DEMO_POSTGRES_PASSWORD",
            "enabled": True,
        },
    )
    assert code in (200, 201), created
    return created["connector"]["id"]


def postgres_connector_pass(cid: str) -> None:
    code, test = req("POST", f"/api/v1/connectors/{cid}/test", {})
    assert code == 200, test
    assert test.get("status") in {"SUCCESS", "OK", "CONNECTED", "connected"}, test
    code, schemas = req("GET", f"/api/v1/connectors/{cid}/schemas?refresh=false")
    assert code == 200 and schemas.get("schemas"), schemas
    schema = schemas["schemas"][0]["name"]
    code, tables = req("GET", f"/api/v1/connectors/{cid}/tables?schema={schema}&refresh=false")
    assert code == 200 and tables.get("tables"), tables
    table = next(t["name"] for t in tables["tables"] if t["name"] == "sales")
    code, desc = req("POST", f"/api/v1/connectors/{cid}/metadata/describe", {"schema": schema, "table": table})
    assert code == 200, desc
    cols = desc.get("columns") or (desc.get("table") or {}).get("columns")
    assert cols, desc
    code, prev = req(
        "POST",
        f"/api/v1/connectors/{cid}/metadata/preview",
        {"schema": schema, "table": table, "limit": 5},
    )
    assert code == 200, prev
    preview = prev.get("preview") or prev
    assert preview.get("rows"), prev
    RESULTS["POSTGRES_CONNECTOR_LIVE_PASS"] = "PASS"


def semantic_lifecycle_pass(cid: str) -> str:
    model_key = f"generic_sales_{uuid.uuid4().hex[:6]}"
    code, model = req("POST", "/api/v1/semantic/models", {"name": "Generic Sales", "key": model_key})
    assert code in (200, 201), model
    mid = model["model"]["id"]
    code, ver = req("POST", f"/api/v1/semantic/models/{mid}/versions", {})
    assert code in (200, 201), ver
    vid = ver["version"]["id"]
    code, ent = req(
        "POST",
        f"/api/v1/semantic/versions/{vid}/entities",
        {
            "key": "sales_fact",
            "name": "Sales",
            "source_type": "logical",
            "db_schema": "public",
            "table_name": "sales",
            "connection_id": cid,
            "primary_key": "sale_id",
        },
    )
    assert code in (200, 201), ent
    code, _ = req(
        "POST",
        f"/api/v1/semantic/versions/{vid}/dimensions",
        {
            "key": "sale_month",
            "name": "Sale month",
            "source_entity_key": "sales_fact",
            "source_column": "sale_date",
            "data_type": "date",
        },
    )
    assert code in (200, 201), _
    code, _ = req(
        "POST",
        f"/api/v1/semantic/versions/{vid}/metrics",
        {
            "key": "total_sales",
            "name": "Total sales",
            "expression": "SUM(amount)",
            "source_entity_key": "sales_fact",
            "aggregation": "sum",
            "format": "currency",
        },
    )
    assert code in (200, 201), _
    code, val = req("POST", f"/api/v1/semantic/versions/{vid}/validate", {"mode": "full"})
    assert code == 200, val
    if not val.get("valid"):
        raise RuntimeError(f"validation failed: {val}")
    code, pub = req("POST", f"/api/v1/semantic/versions/{vid}/publish", {})
    assert code == 200, pub
    code, stage = req("POST", f"/api/v1/semantic/versions/{vid}/runtime/stage", {})
    assert code == 200, stage
    dep_id = stage["deployment"]["id"]
    code, vdep = req("POST", f"/api/v1/semantic/runtime/deployments/{dep_id}/validate", {})
    assert code == 200, vdep
    code, act = req("POST", f"/api/v1/semantic/runtime/deployments/{dep_id}/activate?dry_run=false", {})
    assert code == 200, act
    assert act.get("result") in {"ACTIVATED", "ALREADY_ACTIVE"}, act
    RESULTS["SEMANTIC_LIFECYCLE_LIVE_PASS"] = "PASS"
    return model_key


def ask_data_pass(model_key: str) -> None:
    provider = os.environ.get("CLOSURE_LLM_PROVIDER", "gemini")
    model = os.environ.get("CLOSURE_LLM_MODEL", "gemini-3.8-flash")
    code, resp = req(
        "POST",
        "/chat",
        {
            "question": "What is total sales by month?",
            "session_id": f"closure-{uuid.uuid4().hex[:8]}",
            "provider": provider,
            "model": model,
        },
        timeout=180,
    )
    assert code == 200, resp
    status = resp.get("status")
    if status != "SUCCESS":
        raise RuntimeError(f"Ask Data status={status} strategy={resp.get('strategy')} answer={resp.get('answer')}")
    RESULTS["ASK_DATA_LIVE_PASS"] = "PASS"


def rag_pass() -> None:
    code, ready = req("GET", "/health/ready")
    assert code in (200, 503), ready
    gaps = ready.get("feature_gaps") or []
    if "rag_needs_qdrant" in gaps:
        raise RuntimeError(f"RAG not ready: {gaps}")
    name = f"rag-closure-{uuid.uuid4().hex[:6]}"
    code, lib = req("POST", "/api/v1/libraries", {"name": name})
    assert code in (200, 201), lib
    lid = lib["library"]["id"]
    text = b"Acme Corp refund policy: returns accepted within 30 days of purchase.\n"
    code, up = multipart_upload(lid, "policy.txt", text)
    assert code in (200, 201), up
    doc_id = up["document"]["id"]
    code, proc = req("POST", f"/api/v1/documents/{doc_id}/process", {})
    assert code == 200, proc
    doc = proc.get("document") or proc
    deadline = time.time() + 120
    while doc.get("status") not in {"READY", "ERROR", "FAILED"} and time.time() < deadline:
        time.sleep(2)
        code, polled = req("GET", f"/api/v1/documents/{doc_id}")
        assert code == 200, polled
        doc = polled.get("document") or polled
    if doc.get("status") != "READY":
        raise RuntimeError(f"document not READY: {doc.get('status')} err={doc.get('error_summary')}")
    code, search = req("POST", "/api/v1/retrieval/search", {"query": "refund policy", "library_ids": [lid], "top_k": 3})
    assert code == 200 and search.get("results"), search
    RESULTS["RAG_LIVE_PASS"] = "PASS"
    req("DELETE", f"/api/v1/libraries/{lid}")


def ensure_qdrant_collection() -> None:
    from app.core.config import get_settings
    from app.embeddings.provider import get_embedding_provider
    from app.vectors.store import build_vector_store

    settings = get_settings()
    store = build_vector_store(settings)
    if not store:
        raise RuntimeError("QDRANT_URL not configured")
    embed = get_embedding_provider(settings)
    store.ensure_collection(dimension=embed.dimension)


def main() -> int:
    try:
        ensure_qdrant_collection()
        cid = ensure_demo_connector()
        postgres_connector_pass(cid)
        model_key = semantic_lifecycle_pass(cid)
        ask_data_pass(model_key)
        rag_pass()
    except Exception as exc:
        import traceback

        traceback.print_exc()
        print(f"CLOSURE FAILED: {exc}", file=sys.stderr)
        for k, v in RESULTS.items():
            print(f"{k}={v}")
        return 1
    print(json.dumps(RESULTS, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
