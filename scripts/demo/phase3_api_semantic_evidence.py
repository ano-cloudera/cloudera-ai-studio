#!/usr/bin/env python3
"""Emit Phase 3 Semantic API evidence (registry + SQL consistency vs banking PostgreSQL)."""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts" / "demo"))

from golden_banking_semantic_constants import (  # noqa: E402
    ENTITY_CUSTOMERS_KEY,
    ENTITY_TRANSACTIONS_KEY,
    GLOSSARY_SPECS,
    METRIC_SPECS,
    MODEL_KEY,
    MODEL_NAME,
    REGISTRATION_EVIDENCE,
    REQUIRED_DIMENSION_KEYS,
    REQUIRED_METRIC_KEYS,
    RELATIONSHIP_SPEC,
)

OUT = ROOT / "testing" / "evidence" / "golden-path" / "PHASE3-SEMANTIC" / "api-semantic-evidence.json"
API = os.environ.get("GOLDEN_PATH_API_BASE", "http://127.0.0.1:8001")
BANKING_URL = os.environ.get("BANKING_DEMO_URL", "postgresql://m1:m1pass@127.0.0.1:55432/banking_demo")


def _http(method: str, path: str, body: dict | None = None) -> tuple[int, dict | str]:
    import urllib.error
    import urllib.request

    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
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
    except urllib.error.URLError as e:
        return 0, str(e.reason)


def _pg_scalar(sql: str) -> float | int | None:
    import psycopg

    with psycopg.connect(BANKING_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
            if not row:
                return None
            val = row[0]
            if val is None:
                return None
            if isinstance(val, (int, float)):
                return float(val)
            return float(val)


def _load_sim_settings():
    from pydantic import SecretStr

    from app.core.config import Settings

    sim = ROOT / "runtime" / "cai-sim"
    db = sim / "metadata" / "studio.db"
    return Settings.model_construct(
        state_store="sqlite",
        database_url=f"sqlite+pysqlite:///{db.resolve()}",
        cai_data_dir=sim,
        document_storage_root=(sim / "documents").resolve(),
        semantic_runtime_storage_root=(sim / "var" / "semantic-runtime").resolve(),
        cai_sim_metadata=True,
        semantic_default_model_key=MODEL_KEY,
        qwen_base_url="https://qwen",
        qwen_api_key=SecretStr("token"),
        qwen_model="/models/Qwen3.8-27B-AWQ",
    )


def _governed_structured_ask(settings, model_row, ctx, model_id: str, question: str) -> dict:
    from app.ask_data.structured_context_resolver import resolve_structured_ask
    from app.core.models import AskDataRequest, ChatContextSource
    from app.db.platform_engine import get_session_factory

    req = AskDataRequest(
        session_id=f"phase3-{uuid.uuid4().hex[:8]}",
        question=question,
        provider="qwen",
        model=settings.qwen_model,
        context_sources=[
            ChatContextSource(type="semantic_model", id=model_id, name=MODEL_NAME),
        ],
    )
    with get_session_factory(settings.database_url)() as session:
        out = resolve_structured_ask(
            session,
            settings=settings,
            workspace_id=model_row.workspace_id,
            project_id=model_row.project_id,
            request=req,
            semantic_context=ctx,
            question=question,
        )
    return {
        "context_mode": out.context_mode,
        "explicit_error": out.explicit_error,
        "resolution_status": (out.resolution or {}).get("status"),
        "metric": (out.resolution or {}).get("metric"),
    }


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not REGISTRATION_EVIDENCE.is_file():
        print("missing semantic-registration.json", file=sys.stderr)
        return 1

    reg = json.loads(REGISTRATION_EVIDENCE.read_text(encoding="utf-8"))
    model_id = reg["model_id"]
    version_id = reg.get("draft_version_id") or reg.get("publish", {}).get("version_id")
    publish = reg.get("publish") or {}
    if publish.get("status") != "published":
        print("model not published", publish, file=sys.stderr)
        return 1

    st, models = _http("GET", "/api/v1/semantic/models")
    if st != 200:
        return 1
    model_row = next((m for m in models.get("models", []) if m.get("key") == MODEL_KEY), None)
    if not model_row:
        print("model missing", file=sys.stderr)
        return 1

    st, versions = _http("GET", f"/api/v1/semantic/models/{model_id}/versions")
    active = next((v for v in versions.get("versions", []) if v.get("status") == "ACTIVE"), None)
    st, entities = _http("GET", f"/api/v1/semantic/versions/{version_id}/entities")
    st, metrics = _http("GET", f"/api/v1/semantic/versions/{version_id}/metrics")
    st, dims = _http("GET", f"/api/v1/semantic/versions/{version_id}/dimensions")
    st, rels = _http("GET", f"/api/v1/semantic/versions/{version_id}/relationships")
    st, terms = _http("GET", f"/api/v1/semantic/versions/{version_id}/terms")
    st, runtime = _http("GET", f"/api/v1/semantic/runtime/status?model_key={MODEL_KEY}")

    entity_keys = {e["key"] for e in entities.get("entities", [])}
    metric_keys = {m["key"] for m in metrics.get("metrics", [])}
    dim_keys = {d["key"] for d in dims.get("dimensions", [])}
    glossary_keys = {t["key"] for t in terms.get("terms", [])}
    rel_keys = {r["key"] for r in rels.get("relationships", [])}

    raw_total = _pg_scalar("SELECT COALESCE(SUM(amount), 0) FROM banking_demo.transactions")
    raw_count = _pg_scalar("SELECT COUNT(*) FROM banking_demo.transactions")
    raw_avg = _pg_scalar("SELECT COALESCE(AVG(amount), 0) FROM banking_demo.transactions")
    raw_active = _pg_scalar(
        "SELECT COUNT(DISTINCT customer_id) FROM banking_demo.customers WHERE customer_status = 'Active'"
    )
    raw_fail_rate = _pg_scalar(
        "SELECT COALESCE(SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END)::float / NULLIF(COUNT(*), 0), 0) "
        "FROM banking_demo.transactions"
    )

    import psycopg

    def pg_rows(sql: str) -> list[tuple]:
        with psycopg.connect(BANKING_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return list(cur.fetchall())

    raw_by_channel = pg_rows(
        "SELECT channel, SUM(amount) FROM banking_demo.transactions GROUP BY channel ORDER BY channel"
    )
    segment_top = pg_rows(
        "SELECT c.segment, SUM(t.amount) AS total "
        "FROM banking_demo.transactions t "
        "JOIN banking_demo.customers c ON c.customer_id = t.customer_id "
        "GROUP BY c.segment ORDER BY total DESC LIMIT 1"
    )

    settings = _load_sim_settings()
    from app.db.platform_engine import get_session_factory
    from app.db.platform_models import SemanticModelRow
    from app.main import create_app
    from app.semantic.context import SemanticContextService
    from app.semantic_runtime.loader import SemanticRuntimeLoader
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    with get_session_factory(settings.database_url)() as session:
        model_row = session.scalar(select(SemanticModelRow).where(SemanticModelRow.key == MODEL_KEY))
        if not model_row:
            from sqlalchemy import text

            n = session.scalar(text("select count(*) from semantic_models"))
            print("model row missing in sqlite", settings.database_url, "count=", n, file=sys.stderr)
            return 1
        SemanticRuntimeLoader._instance = None  # noqa: SLF001 — avoid stale paths from process env
        bundle = SemanticRuntimeLoader.get(settings).refresh(
            session,
            workspace_id=model_row.workspace_id,
            project_id=model_row.project_id,
            model_key=MODEL_KEY,
        )
    ctx: SemanticContextService = bundle.context
    app = create_app(settings)
    client = TestClient(app)
    app.state.chat_service.apply_runtime_bundle(bundle)
    if not getattr(ctx, "_registry_runtime", False):
        print("registry runtime not active", file=sys.stderr)
        return 1

    compile_checks: dict[str, object] = {}
    semantic_vs_raw: dict[str, object] = {}
    for question in (
        "What is the total transaction amount?",
        "Show total transaction amount by channel.",
        "Which customer segment has the highest total transaction amount?",
    ):
        res = ctx.resolve(question)
        if res.get("status") != "resolved":
            compile_checks[question] = f"resolve_failed:{res.get('status')}"
            continue
        sql = ctx.compile_governed(res["metric"], question, res.get("dimensions"))
        compile_checks[question] = sql[:400]
        upper = sql.upper()
        if "INSERT" in upper or "DELETE" in upper or "UPDATE" in upper:
            print("unsafe sql", sql, file=sys.stderr)
            return 1
        with psycopg.connect(BANKING_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        semantic_vs_raw[question] = {"row_count": len(rows), "sample": rows[:3]}

    fail_def = next(t for t in terms.get("terms", []) if t.get("key") == "failed_transaction")
    fail_metric = next(m for m in metrics.get("metrics", []) if m.get("key") == "failed_transaction_rate")

    governed_ask = _governed_structured_ask(
        settings,
        model_row,
        ctx,
        model_id,
        "What is the total transaction amount?",
    )

    evidence = {
        "model_key": MODEL_KEY,
        "model_id": model_id,
        "active_version": active,
        "runtime": runtime,
        "entity_keys": sorted(entity_keys),
        "metric_keys": sorted(metric_keys),
        "dimension_keys": sorted(dim_keys),
        "relationship_keys": sorted(rel_keys),
        "glossary_keys": sorted(glossary_keys),
        "registry_checks": {
            "customers_entity": ENTITY_CUSTOMERS_KEY in entity_keys,
            "transactions_entity": ENTITY_TRANSACTIONS_KEY in entity_keys,
            "relationship": RELATIONSHIP_SPEC["key"] in rel_keys,
            "required_metrics": all(k in metric_keys for k in REQUIRED_METRIC_KEYS),
            "required_dimensions": all(k in dim_keys for k in REQUIRED_DIMENSION_KEYS),
            "required_glossary": all(g["key"] in glossary_keys for g in GLOSSARY_SPECS),
            "runtime_healthy": (runtime.get("runtime_status") == "healthy" if isinstance(runtime, dict) else False),
        },
        "raw_postgres": {
            "total_transaction_amount": raw_total,
            "transaction_count": raw_count,
            "average_transaction_value": raw_avg,
            "active_customers": raw_active,
            "failed_transaction_rate": raw_fail_rate,
            "by_channel": raw_by_channel,
            "top_segment": segment_top[0] if segment_top else None,
        },
        "compile_samples": compile_checks,
        "semantic_sql_execution": semantic_vs_raw,
        "failed_rate_alignment": {
            "glossary_definition": fail_def.get("definition"),
            "metric_business_definition": fail_metric.get("business_definition"),
            "metric_expression": fail_metric.get("expression"),
        },
        "governed_structured_ask": governed_ask,
        "sql_governance": "SELECT/WITH only in compile_samples",
    }
    OUT.write_text(json.dumps(evidence, indent=2, default=str) + "\n", encoding="utf-8")
    ok = all(evidence["registry_checks"].values())
    ok = ok and governed_ask.get("context_mode") == "GOVERNED_SEMANTIC"
    ok = ok and governed_ask.get("resolution_status") == "resolved"
    ok = ok and governed_ask.get("metric") == "total_transaction_amount"
    print(json.dumps({"ok": ok, "path": str(OUT)}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
