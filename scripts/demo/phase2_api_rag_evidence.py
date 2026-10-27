#!/usr/bin/env python3
"""Emit Phase 2 Knowledge/RAG API evidence (TestClient + real Qdrant retrieval)."""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "tests"))
sys.path.insert(0, str(ROOT / "scripts" / "demo"))

import httpx  # noqa: E402
from conftest import isolated_settings  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from golden_banking_knowledge_constants import (  # noqa: E402
    LIBRARY_DESCRIPTION,
    LIBRARY_NAME,
    PDF_SEGMENT,
    PDF_TRANSACTION,
)
from pydantic import SecretStr  # noqa: E402

from app.ask_data.table_context_id import encode_raw_table_id  # noqa: E402
from app.chat.context_sources import apply_context_sources  # noqa: E402
from app.core.config import BACKEND_ROOT  # noqa: E402
from app.core.models import AskDataRequest, ChatContextSource, QueryPlan  # noqa: E402
from app.core.models import AnalysisOutput  # noqa: E402
from app.db.platform_engine import get_session_factory  # noqa: E402
from app.db.platform_models import Base  # noqa: E402
from app.main import create_app  # noqa: E402
from app.projects.bootstrap import ensure_platform_seed  # noqa: E402
from app.services.retrieval_service import RetrievalService  # noqa: E402

OUT = ROOT / "testing" / "evidence" / "golden-path" / "PHASE2-KNOWLEDGE" / "api-rag-evidence.json"
INTEGRATION_DATABASE_URL = os.environ.get(
    "GOLDEN_BANKING_DATABASE_URL",
    "postgresql+psycopg://m1:m1pass@127.0.0.1:55432/accelerator",
)


def _qdrant_ready() -> bool:
    url = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")
    try:
        return httpx.get(f"{url.rstrip('/')}/collections", timeout=3.0).status_code == 200
    except Exception:
        return False


def _wait_doc(client: TestClient, doc_id: str) -> dict:
    deadline = time.time() + 90
    while time.time() < deadline:
        doc = client.get(f"/api/v1/documents/{doc_id}").json()["document"]
        if doc["status"] in {"READY", "FAILED"}:
            return doc
        time.sleep(0.25)
    raise TimeoutError(doc_id)


def _seed_library(client: TestClient) -> str:
    library_id = client.post(
        "/api/v1/libraries",
        json={"name": f"{LIBRARY_NAME}-evidence-{uuid.uuid4().hex[:6]}", "description": LIBRARY_DESCRIPTION},
    ).json()["library"]["id"]
    batch = client.post(
        f"/api/v1/libraries/{library_id}/documents/batch-upload",
        files=[
            ("files", (PDF_TRANSACTION.name, PDF_TRANSACTION.read_bytes(), "application/pdf")),
            ("files", (PDF_SEGMENT.name, PDF_SEGMENT.read_bytes(), "application/pdf")),
        ],
    )
    assert batch.status_code == 200, batch.text
    for row in batch.json().get("accepted") or []:
        doc = _wait_doc(client, row["id"])
        assert doc["status"] == "READY", doc
    return library_id


def _fake_sql_provider(sql: str):
    class FakeProvider:
        async def generate_structured(self, _messages, response_model, **_kwargs):
            if response_model is QueryPlan:
                return QueryPlan(strategy="sql_fallback", sql=sql, metrics=[], dimensions=[], filters={})
            return AnalysisOutput(
                direct_answer="raw evidence",
                executive_summary="Phase 2 contrast raw table.",
                insights=[],
                business_implications=[],
                caveats=[],
                data_reference="banking_demo",
                chart_spec=None,
            )

    def _provider(_state, _deps):
        return FakeProvider()

    return _provider


def main() -> int:
    if not PDF_TRANSACTION.is_file() or not PDF_SEGMENT.is_file():
        print("Generate PDFs first: python scripts/demo/generate_banking_knowledge.py", file=sys.stderr)
        return 1
    if not _qdrant_ready():
        print("Qdrant not reachable", file=sys.stderr)
        return 1

    from app.documents.parser import DoclingDocumentParser

    original_parse = DoclingDocumentParser.parse

    def _parse_fast(self, *, path: Path, mime_type: str, document_id: uuid.UUID, title: str):
        return self._fallback(path=path, mime_type=mime_type, document_id=document_id, title=title)

    DoclingDocumentParser.parse = _parse_fast  # type: ignore[method-assign]

    collection = f"golden_p2_ev_{uuid.uuid4().hex[:10]}"
    settings = isolated_settings(
        state_store="postgres",
        database_url=INTEGRATION_DATABASE_URL,
        document_storage_root=ROOT / ".tmp" / "phase2-evidence-docs",
        embedding_provider="mock",
        reranker_provider="none",
        qdrant_collection=collection,
    )
    settings = settings.model_copy(
        update={
            "document_allowed_types": "pdf,txt",
            "document_auto_process": True,
            "qdrant_url": os.environ.get("QDRANT_URL", "http://127.0.0.1:6333"),
            "qwen_base_url": "https://qwen",
            "qwen_api_key": SecretStr("token"),
        }
    )

    engine = __import__("app.db.platform_engine", fromlist=["get_platform_engine"]).get_platform_engine(
        INTEGRATION_DATABASE_URL
    )
    Base.metadata.create_all(engine)
    factory = get_session_factory(INTEGRATION_DATABASE_URL)
    with factory() as session:
        ensure_platform_seed(session, backend_root=BACKEND_ROOT)

    client = TestClient(create_app(settings))
    library_id = _seed_library(client)

    from app.projects.resolver import load_default_project

    project = load_default_project(settings)
    assert project is not None

    retrieval_queries = [
        ("failed_transaction_rate", "How is Failed Transaction Rate defined?", ["attempt", "failed"]),
        ("priority_customer", "What is a Priority Customer?", ["priority"]),
        ("risk_tiers", "What are the three customer risk tiers?", ["low", "medium", "high"]),
        (
            "cross_doc_interpretation",
            "How should a high-risk Priority customer with failed transactions be interpreted?",
            ["priority", "high", "failed"],
        ),
    ]
    retrieval_rows = []
    with factory() as session:
        svc = RetrievalService(settings, session)
        for name, query, needles in retrieval_queries:
            payload = svc.retrieve(
                query=query,
                workspace_id=project.workspace_id,
                project_id=project.id,
                library_ids=[uuid.UUID(library_id)],
                top_k=6,
            )
            blob = " ".join(r.get("text") or "" for r in payload.get("results") or []).casefold()
            retrieval_rows.append(
                {
                    "scenario": name,
                    "query": query,
                    "hit_count": len(payload.get("results") or []),
                    "needles_found": {n: n in blob for n in needles},
                    "filenames": sorted(
                        {r.get("filename") for r in payload.get("results") or [] if r.get("filename")}
                    ),
                }
            )

    with factory() as session:
        rag_ctx = apply_context_sources(
            AskDataRequest(
                session_id="evidence-rag",
                question="What is the definition of a failed transaction?",
                provider="qwen",
                model="/models/Qwen3.8-27B-AWQ",
                context_sources=[
                    ChatContextSource(type="knowledge_library", id=library_id, name=LIBRARY_NAME),
                ],
            ),
            session=session,
            project_id=project.id,
            conversation_history=[],
            settings=settings,
        )

    os.environ.setdefault("BANKING_DEMO_PG_PASSWORD", "m1pass")
    key = f"golden.p2.{uuid.uuid4().hex[:6]}"
    created = client.post(
        "/api/v1/connectors",
        json={
            "name": "Banking PostgreSQL Evidence",
            "key": key,
            "connector_type": "postgres",
            "config": {
                "host": "127.0.0.1",
                "port": 55432,
                "database": "banking_demo",
                "username": "m1",
                "sslmode": "prefer",
            },
            "secret_ref": "env://BANKING_DEMO_PG_PASSWORD",
        },
    )
    tx_id = encode_raw_table_id(
        connector_id=uuid.UUID(created.json()["connector"]["id"]),
        catalog=None,
        schema="banking_demo",
        table="transactions",
    )
    chat_service = client.app.state.chat_service
    with patch("app.graph.workflow._provider", _fake_sql_provider("SELECT COUNT(*) FROM banking_demo.transactions")):
        with patch.object(chat_service, "_prepare_registry_request", side_effect=lambda request, capability=None: request):
            raw_resp = client.post(
                "/chat",
                json={
                    "session_id": "evidence-raw-failed",
                    "question": "How many failed transactions are there?",
                    "provider": "qwen",
                    "model": "/models/Qwen3.8-27B-AWQ",
                    "context_sources": [{"type": "table", "id": tx_id, "name": "transactions"}],
                },
            )

    DoclingDocumentParser.parse = original_parse  # type: ignore[method-assign]

    payload = {
        "library_id": library_id,
        "retrieval": retrieval_rows,
        "routing": {
            "knowledge_mode": rag_ctx.mode,
            "knowledge_library_ids": rag_ctx.library_ids,
            "raw_context_mode": raw_resp.json().get("context_mode"),
            "raw_strategy": raw_resp.json().get("strategy"),
        },
        "retrieval_ok": all(
            row["hit_count"] > 0 and all(row["needles_found"].values()) for row in retrieval_rows
        ),
        "contrast_ok": rag_ctx.mode == "rag" and raw_resp.json().get("context_mode") == "RAW_TABLE",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}")
    ok = payload["retrieval_ok"] and payload["contrast_ok"]
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
