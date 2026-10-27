"""Golden Path Banking Demo — Phase 2 (Knowledge / RAG)."""
from __future__ import annotations

import io
import os
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "demo"))

from golden_banking_knowledge_constants import (  # noqa: E402
    LIBRARY_DESCRIPTION,
    LIBRARY_NAME,
    PDF_SEGMENT,
    PDF_TRANSACTION,
)

from app.chat.context_sources import apply_context_sources, structured_data_sources  # noqa: E402
from app.core.config import BACKEND_ROOT, Settings  # noqa: E402
from app.core.models import AskDataRequest, AskDataResponse, ChatContextSource, QueryData, Timings  # noqa: E402
from app.core.models import AnalysisOutput  # noqa: E402
from app.db.platform_engine import get_session_factory  # noqa: E402
from app.db.platform_models import Base  # noqa: E402
from app.main import create_app  # noqa: E402
from app.projects.bootstrap import ensure_platform_seed  # noqa: E402
from app.services.retrieval_service import RetrievalService  # noqa: E402

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


skip_no_qdrant = pytest.mark.skipif(not _qdrant_ready(), reason="Qdrant not reachable")
requires_platform_db = pytest.mark.skipif(
    os.environ.get("GOLDEN_BANKING_RUN_INTEGRATION", "1") != "1",
    reason="Set GOLDEN_BANKING_RUN_INTEGRATION=1",
)


@pytest.fixture(autouse=True)
def _fast_pdf_ingestion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid heavy Docling startup in integration tests; PDFs still use pypdf fallback path."""

    from app.documents.parser import DoclingDocumentParser

    def _parse_fast(self, *, path: Path, mime_type: str, document_id: uuid.UUID, title: str):
        return self._fallback(path=path, mime_type=mime_type, document_id=document_id, title=title)

    monkeypatch.setattr(DoclingDocumentParser, "parse", _parse_fast)


@pytest.fixture()
def knowledge_client(tmp_path):
    url = INTEGRATION_DATABASE_URL
    engine = __import__("app.db.platform_engine", fromlist=["get_platform_engine"]).get_platform_engine(url)
    Base.metadata.create_all(engine)
    factory = get_session_factory(url)
    with factory() as session:
        ensure_platform_seed(session, backend_root=BACKEND_ROOT)

    from app.db.metadata_db import is_sqlite_metadata_url

    collection = f"golden_k_{uuid.uuid4().hex[:10]}"
    settings = Settings(
        _env_file=None,
        state_store="sqlite" if is_sqlite_metadata_url(url) else "postgres",
        database_url=url,
        document_storage_root=tmp_path / "docs",
        document_allowed_types="pdf,txt",
        document_auto_process=True,
        embedding_provider="mock",
        reranker_provider="none",
        qdrant_url=os.environ.get("QDRANT_URL", "http://127.0.0.1:6333"),
        qdrant_collection=collection,
        knowledge_upload_max_files_per_batch=10,
        qwen_base_url="https://qwen",
        qwen_api_key=SecretStr("token"),
        qwen_model="/models/Qwen3.8-27B-AWQ",
    )
    return TestClient(create_app(settings)), settings, factory


def _wait_doc(client: TestClient, doc_id: str) -> dict:
    deadline = time.time() + 60
    while time.time() < deadline:
        doc = client.get(f"/api/v1/documents/{doc_id}").json()["document"]
        if doc["status"] in {"READY", "FAILED"}:
            return doc
        time.sleep(0.25)
    raise AssertionError("document timeout")


def _seed_library(client: TestClient, *, name: str | None = None) -> tuple[str, list[str]]:
    assert PDF_TRANSACTION.is_file() and PDF_SEGMENT.is_file()
    lib_name = name or f"{LIBRARY_NAME}-{uuid.uuid4().hex[:6]}"
    library_id = client.post(
        "/api/v1/libraries",
        json={"name": lib_name, "description": LIBRARY_DESCRIPTION},
    ).json()["library"]["id"]
    batch = client.post(
        f"/api/v1/libraries/{library_id}/documents/batch-upload",
        files=[
            ("files", (PDF_TRANSACTION.name, PDF_TRANSACTION.read_bytes(), "application/pdf")),
            ("files", (PDF_SEGMENT.name, PDF_SEGMENT.read_bytes(), "application/pdf")),
        ],
    )
    assert batch.status_code == 200, batch.text
    body = batch.json()
    assert len(body.get("accepted") or []) == 2
    assert body.get("requested") == 2
    doc_ids = [row["id"] for row in body["accepted"]]
    docs = [_wait_doc(client, doc_id) for doc_id in doc_ids]
    assert all(d["status"] == "READY" for d in docs)
    assert all(int(d.get("chunk_count") or 0) > 0 for d in docs)
    return library_id, doc_ids


def test_demo_pdfs_exist_and_extractable():
    assert PDF_TRANSACTION.is_file()
    assert PDF_SEGMENT.is_file()
    from pypdf import PdfReader

    for path in (PDF_TRANSACTION, PDF_SEGMENT):
        reader = PdfReader(str(path))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        assert "Golden Demo" in text or "demo" in text.casefold()
        assert len(text) > 500


@requires_platform_db
@skip_no_qdrant
def test_batch_upload_two_pdfs_indexed(knowledge_client):
    client, _, _ = knowledge_client
    library_id, doc_ids = _seed_library(client)
    listed = client.get(f"/api/v1/libraries/{library_id}/documents?page=1&page_size=10")
    assert listed.json()["total"] == 2
    assert len(doc_ids) == 2


@requires_platform_db
@skip_no_qdrant
def test_retrieval_grounding_concepts(knowledge_client):
    client, settings, factory = knowledge_client
    library_id, _ = _seed_library(client)
    project = __import__("app.projects.resolver", fromlist=["load_default_project"]).load_default_project(settings)
    assert project is not None
    with factory() as session:
        svc = RetrievalService(settings, session)
        payload = svc.retrieve(
            query="How is Failed Transaction Rate defined?",
            workspace_id=project.workspace_id,
            project_id=project.id,
            library_ids=[uuid.UUID(library_id)],
            top_k=5,
        )
    texts = " ".join(row.get("text") or "" for row in payload.get("results") or []).casefold()
    assert "failed" in texts and "transaction" in texts
    assert "attempt" in texts or "total" in texts

    with factory() as session:
        svc2 = RetrievalService(settings, session)
        payload2 = svc2.retrieve(
            query="What is a Priority Customer?",
            workspace_id=project.workspace_id,
            project_id=project.id,
            library_ids=[uuid.UUID(library_id)],
            top_k=5,
        )
    text2 = " ".join(row.get("text") or "" for row in payload2.get("results") or []).casefold()
    assert "priority" in text2


@requires_platform_db
def test_explicit_knowledge_context_routes_to_rag(knowledge_client):
    client, settings, factory = knowledge_client
    library_id = client.post(
        "/api/v1/libraries",
        json={"name": f"{LIBRARY_NAME}-{uuid.uuid4().hex[:6]}", "description": LIBRARY_DESCRIPTION},
    ).json()["library"]["id"]
    with factory() as session:
        from app.projects.resolver import load_default_project

        project = load_default_project(settings)
        assert project is not None
        req = AskDataRequest(
            session_id="s",
            question="What does Failed transaction mean?",
            provider="qwen",
            model="/models/Qwen3.8-27B-AWQ",
            context_sources=[
                ChatContextSource(type="knowledge_library", id=library_id, name=LIBRARY_NAME),
            ],
        )
        out = apply_context_sources(
            req,
            session=session,
            project_id=project.id,
            conversation_history=[],
            settings=settings,
        )
    assert out.mode == "rag"
    assert out.library_ids == [library_id]
    assert structured_data_sources(out.context_sources) == []


@requires_platform_db
@skip_no_qdrant
def test_knowledge_chat_stream_rag_with_citations(knowledge_client):
    client, _, _ = knowledge_client
    library_id, _ = _seed_library(client)
    from app.core.models import CitationRecord

    stub = AskDataResponse(
        request_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        status="SUCCESS",
        provider="qwen",
        model="/models/Qwen3.8-27B-AWQ",
        strategy="rag",
        route="rag",
        grounding="SUPPORTED",
        answer=AnalysisOutput(
            direct_answer="Channels include Mobile Banking, Internet Banking, ATM, Branch, and EDC.",
            executive_summary="Policy lists five channels.",
            insights=[],
            business_implications=[],
            caveats=[],
            data_reference="retrieved document evidence",
            chart_spec=None,
        ),
        data=QueryData(),
        chart_spec=None,
        timings=Timings(total_ms=3),
        citations=[
            CitationRecord(
                document_id=str(uuid.uuid4()),
                filename="Retail Banking Transaction Policy.pdf",
                page_number=2,
                section=None,
                chunk_id=str(uuid.uuid4()),
                source_uri=None,
                snippet="Mobile Banking, Internet Banking, ATM, Branch, EDC",
                score=0.91,
            )
        ],
    )

    async def fake_run(body, **_kwargs):
        return stub

    with patch("app.api.chat._validate_selection", lambda *_a, **_k: None):
        with patch.object(client.app.state.chat_service, "run", fake_run):
            response = client.post(
                "/chat",
                json={
                    "session_id": str(uuid.uuid4()),
                    "question": "Which transaction channels are defined in the policy?",
                    "provider": "qwen",
                    "model": "/models/Qwen3.8-27B-AWQ",
                    "context_sources": [
                        {"type": "knowledge_library", "id": library_id, "name": LIBRARY_NAME},
                    ],
                },
            )
    assert response.status_code == 200
    body = response.json()
    assert body["strategy"] == "rag"
    assert body["route"] == "rag"
    assert "Mobile Banking" in body["answer"]["direct_answer"]
    assert body["citations"]
    assert "Retail Banking Transaction Policy.pdf" in body["citations"][0]["filename"]


@requires_platform_db
@skip_no_qdrant
def test_mixed_knowledge_and_table_rejected(knowledge_client):
    client, _, _ = knowledge_client
    library_id, _ = _seed_library(client)
    table_id = "tr:00000000-0000-0000-0000-000000000001:-:banking_demo:transactions"
    response = client.post(
        "/chat/stream",
        json={
            "session_id": str(uuid.uuid4()),
            "question": "mixed",
            "provider": "qwen",
            "model": "/models/Qwen3.8-27B-AWQ",
            "context_sources": [
                {"type": "knowledge_library", "id": library_id, "name": LIBRARY_NAME},
                {"type": "table", "id": table_id, "name": "transactions"},
            ],
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "mixed_context_unsupported"


@requires_platform_db
@skip_no_qdrant
def test_knowledge_rag_not_raw_table_route(knowledge_client):
    client, _, _ = knowledge_client
    library_id, _ = _seed_library(client)
    stub = AskDataResponse(
        request_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        status="SUCCESS",
        provider="qwen",
        model="/models/Qwen3.8-27B-AWQ",
        strategy="rag",
        route="rag",
        grounding="SUPPORTED",
        answer=AnalysisOutput(
            direct_answer="Failed means not completed successfully.",
            executive_summary="Policy definition.",
            insights=[],
            business_implications=[],
            caveats=[],
            data_reference="retrieved document evidence",
            chart_spec=None,
        ),
        data=QueryData(),
        chart_spec=None,
        timings=Timings(total_ms=5),
        citations=[],
        context_mode=None,
    )

    async def fake_run(body, **_kwargs):
        return stub

    with patch("app.api.chat._validate_selection", lambda *_a, **_k: None):
        with patch.object(client.app.state.chat_service, "run", fake_run):
            with patch("app.graph.workflow.build_workflow") as wf:
                resp = client.post(
                    "/chat",
                    json={
                        "session_id": str(uuid.uuid4()),
                        "question": "What is the definition of a failed transaction?",
                        "provider": "qwen",
                        "model": "/models/Qwen3.8-27B-AWQ",
                        "context_sources": [
                            {"type": "knowledge_library", "id": library_id, "name": LIBRARY_NAME},
                        ],
                    },
                )
            assert resp.status_code == 200
            wf.assert_not_called()
    body = resp.json()
    assert body["strategy"] == "rag"
    assert body.get("context_mode") is None
    assert "Failed means" in body["answer"]["direct_answer"]
