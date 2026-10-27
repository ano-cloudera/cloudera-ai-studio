#!/usr/bin/env python3
"""M2 release closure smoke (API-level, local Postgres + Qdrant)."""

from __future__ import annotations

import io
import json
import os
import sys
import time
import uuid
from contextlib import contextmanager

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pydantic import SecretStr

from app.core.config import BACKEND_ROOT, Settings
from app.core.models import AnalysisOutput, AskDataRequest, AskDataResponse, QueryData, Timings
from app.db.platform_engine import get_platform_engine, get_session_factory
from app.db.platform_models import Base, DocumentChunkRow
from app.main import create_app
from app.projects.bootstrap import ensure_platform_seed
from app.rag.models import RagLlmOutput
from fastapi.testclient import TestClient
from sqlalchemy import func, select


def _fail(msg: str) -> int:
    print(f"M2_SMOKE_FAIL: {msg}")
    return 1


def main() -> int:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return _fail("DATABASE_URL not set")
    qdrant = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333").strip()
    collection = os.environ.get("QDRANT_COLLECTION", f"m2_close_{uuid.uuid4().hex[:8]}")

    engine = get_platform_engine(url)
    Base.metadata.create_all(engine)
    factory = get_session_factory(url)
    with factory() as session:
        ensure_platform_seed(session, backend_root=BACKEND_ROOT)

    tmp = ROOT / "runtime" / "m2_closure_smoke"
    tmp.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        _env_file=None,
        state_store="postgres",
        database_url=url,
        document_storage_root=tmp / "docs",
        embedding_provider=os.environ.get("EMBEDDING_PROVIDER", "mock"),
        reranker_provider=os.environ.get("RERANKER_PROVIDER", "none"),
        qdrant_url=qdrant,
        qdrant_collection=collection,
        qwen_base_url="https://qwen.example",
        qwen_api_key=SecretStr("token"),
        qwen_model="qwen-model",
    )
    client = TestClient(create_app(settings))
    session_id = str(uuid.uuid4())

    # Knowledge: library + upload (txt stands in for PDF path; parser accepts plain text)
    lib = client.post("/api/v1/libraries", json={"name": f"M2-Close-{uuid.uuid4().hex[:6]}"})
    if lib.status_code != 200:
        return _fail(f"create library {lib.status_code} {lib.text}")
    library_id = lib.json()["library"]["id"]

    # Plain-text upload for reliable local smoke (PDF path covered by M2B parser tests when pypdf/docling present).
    body = (b"M2 closure policy cap 9000 for travel reimbursement. " * 20)
    upload = client.post(
        f"/api/v1/libraries/{library_id}/documents",
        files={"file": ("closure-policy.txt", io.BytesIO(body), "text/plain")},
    )
    if upload.status_code != 200:
        return _fail(f"upload {upload.status_code} {upload.text}")
    doc = upload.json()["document"]
    doc_id = doc["id"]
    if doc["status"] not in {"QUEUED", "UPLOADED", "PROCESSING", "READY"}:
        return _fail(f"unexpected upload status {doc['status']}")

    deadline = time.time() + 45
    final_status = "UNKNOWN"
    while time.time() < deadline:
        row = client.get(f"/api/v1/documents/{doc_id}").json()["document"]
        final_status = row["status"]
        if final_status in {"READY", "FAILED"}:
            break
        time.sleep(0.25)
    if final_status != "READY":
        return _fail(f"document not READY (status={final_status})")

    with factory() as session:
        chunk_count = session.scalar(
            select(func.count()).select_from(DocumentChunkRow).where(DocumentChunkRow.document_id == uuid.UUID(doc_id))
        )
    if not chunk_count:
        return _fail("no document_chunks in PostgreSQL")

    search = client.post(
        "/api/v1/retrieval/search",
        json={"query": "policy cap 9000", "library_ids": [library_id], "top_k": 5},
    )
    if search.status_code != 200 or not search.json().get("results"):
        return _fail(f"retrieval search failed {search.status_code} {search.text[:200]}")

    chunk_id = search.json()["results"][0]["chunk_id"]
    app = client.app
    chat_svc = app.state.chat_service

    @contextmanager
    def llm_patch(mode: str):
        class _FakeLLM:
            provider_name = "qwen"

            async def generate_structured(self, messages, response_model, **kwargs):
                if mode == "insufficient":
                    return RagLlmOutput(
                        grounding="INSUFFICIENT_EVIDENCE",
                        direct_answer="hallucination",
                        executive_summary="hallucination",
                        cited_chunk_ids=[],
                    )
                return RagLlmOutput(
                    grounding="SUPPORTED",
                    direct_answer="The policy cap is 9000.",
                    executive_summary="Cap is 9000 per closure policy.",
                    cited_chunk_ids=[chunk_id],
                )

        original = chat_svc._resolve_provider

        def _resolve(request, request_id):
            return _FakeLLM()

        chat_svc._resolve_provider = _resolve
        try:
            yield
        finally:
            chat_svc._resolve_provider = original

    with llm_patch("grounded"):
        rag1 = client.post(
            "/chat",
            json={
                "session_id": session_id,
                "question": "What is the policy cap?",
                "provider": "qwen",
                "model": "qwen-model",
                "mode": "rag",
                "library_ids": [library_id],
            },
        )
    if rag1.status_code != 200:
        return _fail(f"rag chat {rag1.status_code} {rag1.text[:300]}")
    body1 = rag1.json()
    if body1.get("strategy") != "rag" or body1.get("grounding") != "SUPPORTED":
        return _fail(f"rag grounding unexpected {json.dumps({k: body1.get(k) for k in ('strategy','grounding','status')})}")
    cites = body1.get("citations") or []
    if not cites or cites[0].get("chunk_id") != chunk_id:
        return _fail("citation not tied to retrieved chunk")

    with llm_patch("insufficient"):
        rag_neg = client.post(
            "/chat",
            json={
                "session_id": session_id,
                "question": "What is the CEO salary?",
                "provider": "qwen",
                "model": "qwen-model",
                "mode": "rag",
                "library_ids": [library_id],
            },
        )
    neg = rag_neg.json()
    if neg.get("grounding") != "INSUFFICIENT_EVIDENCE" and neg.get("status") != "NO_DATA":
        return _fail("insufficient-evidence path not enforced")
    if "9000" in (neg.get("answer") or {}).get("direct_answer", "") and neg.get("grounding") == "INSUFFICIENT_EVIDENCE":
        pass  # template answer ok
    if neg.get("citations"):
        return _fail("insufficient response should not include citations")

    history = chat_svc.history.load(session_id, limit=8)
    from app.rag.scope import rag_scope_from_history

    if not rag_scope_from_history(history):
        return _fail("follow-up lost library scope in session history")

    with llm_patch("grounded"):
        rag2 = client.post(
            "/chat",
            json={
                "session_id": session_id,
                "question": "And the maximum amount?",
                "provider": "qwen",
                "model": "qwen-model",
                "mode": "rag",
            },
        )
    if rag2.status_code != 200:
        return _fail(f"follow-up rag failed {rag2.status_code}")

    # Ask Data default mode unchanged (expect non-rag strategy)
    ask = client.post(
        "/chat",
        json={
            "session_id": str(uuid.uuid4()),
            "question": "hello",
            "provider": "qwen",
            "model": "qwen-model",
        },
    )
    if ask.status_code != 200:
        return _fail(f"ask data chat {ask.status_code}")
    if ask.json().get("strategy") == "rag":
        return _fail("default chat mode routed to rag")

    print(
        json.dumps(
            {
                "status": "M2_SMOKE_OK",
                "library_id": library_id,
                "document_id": doc_id,
                "document_status": final_status,
                "postgres_chunks": int(chunk_count),
                "retrieval_hits": len(search.json().get("results") or []),
                "rag_grounding": body1.get("grounding"),
                "citation_chunk_id": cites[0].get("chunk_id") if cites else None,
                "insufficient_status": neg.get("status"),
                "ask_data_strategy": ask.json().get("strategy"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
