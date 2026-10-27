from __future__ import annotations

import io
import os
import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr
from fastapi.testclient import TestClient

from app.core.config import BACKEND_ROOT, Settings
from app.core.models import AnalysisOutput, AskDataRequest, AskDataResponse, QueryData, Timings
from app.db.platform_engine import get_session_factory
from app.db.platform_models import Base
from app.main import create_app
from app.projects.bootstrap import ensure_platform_seed

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set",
)


@pytest.fixture()
def m2d_client(tmp_path):
    url = os.environ["DATABASE_URL"]
    qdrant_url = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")
    engine = __import__("app.db.platform_engine", fromlist=["get_platform_engine"]).get_platform_engine(url)
    Base.metadata.create_all(engine)
    factory = get_session_factory(url)
    with factory() as session:
        ensure_platform_seed(session, backend_root=BACKEND_ROOT)

    settings = Settings(
        _env_file=None,
        state_store="postgres",
        database_url=url,
        document_storage_root=tmp_path / "docs",
        embedding_provider="mock",
        reranker_provider="none",
        qdrant_url=qdrant_url,
        qdrant_collection=f"m2d_{uuid.uuid4().hex[:8]}",
        qwen_base_url="https://qwen",
        qwen_api_key=SecretStr("token"),
        qwen_model="qwen-model",
    )
    return TestClient(create_app(settings)), settings


def _wait_ready(client: TestClient, doc_id: str) -> None:
    deadline = time.time() + 30
    while time.time() < deadline:
        status = client.get(f"/api/v1/documents/{doc_id}").json()["document"]["status"]
        if status in {"READY", "FAILED"}:
            return
        time.sleep(0.2)
    raise AssertionError("timeout")


def test_chat_stream_rag_mode_routes(m2d_client):
    client, _ = m2d_client
    library_id = client.post("/api/v1/libraries", json={"name": f"RAG-{uuid.uuid4().hex[:6]}"}).json()["library"]["id"]
    content = ("Reimbursement maximum amount is 5000 USD for travel. " * 15).encode()
    upload = client.post(
        f"/api/v1/libraries/{library_id}/documents",
        files={"file": ("policy.txt", io.BytesIO(content), "text/plain")},
    )
    doc_id = upload.json()["document"]["id"]
    _wait_ready(client, doc_id)

    stub_response = AskDataResponse(
        request_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        status="SUCCESS",
        provider="qwen",
        model="qwen-model",
        strategy="rag",
        route="rag",
        grounding="SUPPORTED",
        answer=AnalysisOutput(
            direct_answer="Maximum reimbursement is 5000 USD.",
            executive_summary="Cap is 5000 USD.",
            insights=[],
            business_implications=[],
            caveats=[],
            data_reference="retrieved document evidence",
            chart_spec=None,
        ),
        data=QueryData(),
        chart_spec=None,
        timings=Timings(total_ms=12),
        citations=[],
    )

    async def fake_stream(*_args, **_kwargs):
        yield {"type": "progress", "stage": "retrieve", "label": "Searching knowledge", "detail": None}
        yield {
            "type": "done",
            "response": stub_response,
            "session_frame": {"mode": "rag", "rag_library_ids": [library_id]},
        }

    with patch("app.services.chat.stream_rag_turn", fake_stream):
        response = client.post(
            "/chat/stream",
            json={
                "session_id": str(uuid.uuid4()),
                "question": "What is the maximum reimbursement?",
                "provider": "qwen",
                "model": "qwen-model",
                "mode": "rag",
                "library_ids": [library_id],
            },
        )
        assert response.status_code == 200
        assert "Maximum reimbursement" in response.text


def test_ask_data_request_default_mode_unchanged():
    req = AskDataRequest(
        session_id="s",
        question="q",
        provider="qwen",
        model="m",
    )
    assert req.mode == "ask_data"
    assert req.library_ids is None
