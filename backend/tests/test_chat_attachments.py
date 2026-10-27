from __future__ import annotations

import io
import os
import time
import uuid

import pytest
from pydantic import SecretStr
from fastapi.testclient import TestClient

from app.core.config import BACKEND_ROOT, Settings
from app.db.platform_engine import get_session_factory
from app.db.platform_models import Base
from app.main import create_app
from app.projects.bootstrap import ensure_platform_seed

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set",
)


@pytest.fixture()
def attachment_client(tmp_path):
    url = os.environ["DATABASE_URL"]
    engine = __import__("app.db.platform_engine", fromlist=["get_platform_engine"]).get_platform_engine(url)
    Base.metadata.create_all(engine)
    factory = get_session_factory(url)
    with factory() as session:
        ensure_platform_seed(session, backend_root=BACKEND_ROOT)

    os.environ["STATE_STORE"] = "postgres"
    os.environ["DATABASE_URL"] = url
    settings = Settings(
        _env_file=None,
        document_storage_root=tmp_path / "docs",
        embedding_provider="mock",
        reranker_provider="none",
        qdrant_url=os.environ.get("QDRANT_URL", ""),
        qdrant_collection=f"att_{uuid.uuid4().hex[:8]}",
        document_auto_process=True,
        qwen_base_url="https://qwen",
        qwen_api_key=SecretStr("token"),
        qwen_model="qwen-model",
    )
    return TestClient(create_app(settings)), settings


def _wait_attachment(client: TestClient, attachment_id: str) -> dict:
    deadline = time.time() + 30
    while time.time() < deadline:
        payload = client.get(f"/api/v1/chat/attachments/{attachment_id}").json()["attachment"]
        if payload["status"] in {"READY", "FAILED", "EXPIRED"}:
            return payload
        time.sleep(0.25)
    raise AssertionError("attachment processing timeout")


def test_attachment_txt_upload_and_status(attachment_client):
    client, _ = attachment_client
    session_id = str(uuid.uuid4())
    content = b"Quarterly revenue grew 12 percent year over year in the report."
    response = client.post(
        "/api/v1/chat/attachments/batch",
        data={"session_id": session_id},
        files=[("files", ("report.txt", io.BytesIO(content), "text/plain"))],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"]
    att_id = body["accepted"][0]["id"]
    final = _wait_attachment(client, att_id)
    assert final["status"] == "READY"


def test_attachment_unsupported_type_rejected(attachment_client):
    client, _ = attachment_client
    response = client.post(
        "/api/v1/chat/attachments/batch",
        data={"session_id": "s1"},
        files=[("files", ("malware.exe", io.BytesIO(b"MZ"), "application/octet-stream"))],
    )
    assert response.status_code == 200
    assert response.json()["accepted"] == []
    assert response.json()["rejected"]


def test_mixed_context_sources_rejected(attachment_client):
    client, _ = attachment_client
    library_id = client.post("/api/v1/libraries", json={"name": f"L-{uuid.uuid4().hex[:6]}"}).json()["library"]["id"]
    response = client.post(
        "/chat/stream",
        json={
            "session_id": str(uuid.uuid4()),
            "question": "Summarize",
            "provider": "qwen",
            "model": "qwen-model",
            "context_sources": [
                {"type": "knowledge_library", "id": library_id, "name": "Lib"},
                {"type": "uploaded_file", "id": str(uuid.uuid4()), "name": "x.pdf"},
            ],
        },
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "mixed_context_unsupported"


FIXTURES = BACKEND_ROOT / "tests" / "fixtures" / "chat_attachments"


@pytest.mark.parametrize(
    "filename",
    ["sample.txt", "sample.md", "sample.pdf", "sample.docx"],
)
def test_attachment_supported_types_reach_ready(attachment_client, filename):
    client, _ = attachment_client
    data = (FIXTURES / filename).read_bytes()
    response = client.post(
        "/api/v1/chat/attachments/batch",
        data={"session_id": str(uuid.uuid4())},
        files=[("files", (filename, io.BytesIO(data), "application/octet-stream"))],
    )
    assert response.status_code == 200
    assert response.json()["accepted"]
    att_id = response.json()["accepted"][0]["id"]
    final = _wait_attachment(client, att_id)
    assert final["status"] == "READY"


def test_attachment_expires_at_set(attachment_client):
    client, settings = attachment_client
    upload = client.post(
        "/api/v1/chat/attachments/batch",
        data={"session_id": str(uuid.uuid4())},
        files=[("files", ("ttl.txt", io.BytesIO(b"ttl check"), "text/plain"))],
    )
    att_id = upload.json()["accepted"][0]["id"]
    row = client.get(f"/api/v1/chat/attachments/{att_id}").json()["attachment"]
    assert row["expires_at"]
    assert settings.chat_attachment_ttl_days >= 1


def test_cleanup_expired_attachment(attachment_client):
    client, settings = attachment_client
    upload = client.post(
        "/api/v1/chat/attachments/batch",
        data={"session_id": str(uuid.uuid4())},
        files=[("files", ("cleanup.txt", io.BytesIO(b"cleanup me"), "text/plain"))],
    )
    att_id = upload.json()["accepted"][0]["id"]
    _wait_attachment(client, att_id)

    from datetime import datetime, timedelta, timezone

    from app.db.platform_models import ChatAttachmentRow
    from app.services.chat_attachment_cleanup import cleanup_expired_attachments

    factory = get_session_factory(settings.database_url)
    with factory() as session:
        row = session.get(ChatAttachmentRow, uuid.UUID(att_id))
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        session.add(row)
        session.commit()
        result = cleanup_expired_attachments(settings, session)
        assert result["deleted"] >= 1
    assert client.get(f"/api/v1/chat/attachments/{att_id}").status_code == 404


def test_attachment_expired_blocked(attachment_client):
    client, settings = attachment_client
    content = b"Expired attachment unique phrase for M9."
    upload = client.post(
        "/api/v1/chat/attachments/batch",
        data={"session_id": str(uuid.uuid4())},
        files=[("files", ("expired.txt", io.BytesIO(content), "text/plain"))],
    )
    att_id = upload.json()["accepted"][0]["id"]
    _wait_attachment(client, att_id)

    factory = get_session_factory(settings.database_url)
    from datetime import datetime, timedelta, timezone
    from app.db.platform_models import ChatAttachmentRow

    with factory() as session:
        row = session.get(ChatAttachmentRow, uuid.UUID(att_id))
        row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        session.add(row)
        session.commit()

    response = client.post(
        "/chat/stream",
        json={
            "session_id": str(uuid.uuid4()),
            "question": "Summarize",
            "provider": "qwen",
            "model": "qwen-model",
            "context_sources": [{"type": "uploaded_file", "id": att_id, "name": "expired.txt"}],
        },
    )
    assert response.status_code == 410
    assert response.json()["detail"]["code"] == "ATTACHMENT_EXPIRED"


def test_attachment_delete_removes_record(attachment_client):
    client, _ = attachment_client
    upload = client.post(
        "/api/v1/chat/attachments/batch",
        data={"session_id": "s-del"},
        files=[("files", ("del.txt", io.BytesIO(b"delete me please"), "text/plain"))],
    )
    att_id = upload.json()["accepted"][0]["id"]
    assert client.delete(f"/api/v1/chat/attachments/{att_id}").status_code == 200
    assert client.get(f"/api/v1/chat/attachments/{att_id}").status_code == 404


def test_save_to_knowledge_idempotent(attachment_client):
    client, _ = attachment_client
    upload = client.post(
        "/api/v1/chat/attachments/batch",
        data={"session_id": "s-save"},
        files=[("files", ("save-me.txt", io.BytesIO(b"Save to knowledge fixture content."), "text/plain"))],
    )
    att_id = upload.json()["accepted"][0]["id"]
    _wait_attachment(client, att_id)
    library_id = client.post("/api/v1/libraries", json={"name": f"Save-{uuid.uuid4().hex[:6]}"}).json()["library"]["id"]
    first = client.post(
        f"/api/v1/chat/attachments/{att_id}/save-to-knowledge",
        json={"library_id": library_id},
    )
    assert first.status_code == 200
    second = client.post(
        f"/api/v1/chat/attachments/{att_id}/save-to-knowledge",
        json={"library_id": library_id},
    )
    assert second.status_code == 200
    assert second.json()["saved"]["document_id"] == first.json()["saved"]["document_id"]


def test_unsupported_types_rejected_with_code(attachment_client):
    client, _ = attachment_client
    for name, payload in [
        ("notes.csv", b"a,b\n1,2"),
        ("pic.png", b"\x89PNG\r\n\x1a\n"),
    ]:
        response = client.post(
            "/api/v1/chat/attachments/batch",
            data={"session_id": "s1"},
            files=[("files", (name, io.BytesIO(payload), "application/octet-stream"))],
        )
        body = response.json()
        assert not body["accepted"]
        assert body["rejected"][0]["code"] == "ATTACHMENT_TYPE_UNSUPPORTED"


def test_attachment_cross_project_access_denied(attachment_client):
    client, settings = attachment_client
    upload = client.post(
        "/api/v1/chat/attachments/batch",
        data={"session_id": str(uuid.uuid4())},
        files=[("files", ("iso.txt", io.BytesIO(b"project scope"), "text/plain"))],
    )
    att_id = upload.json()["accepted"][0]["id"]
    _wait_attachment(client, att_id)

    from app.db.platform_models import ProjectRow, WorkspaceRow
    from app.services.chat_attachment_service import ChatAttachmentService, ChatAttachmentServiceError

    factory = get_session_factory(settings.database_url)
    with factory() as session:
        ws = session.execute(__import__("sqlalchemy").select(WorkspaceRow).limit(1)).scalar_one()
        other = ProjectRow(
            workspace_id=ws.id,
            name="M9-Other",
            slug=f"m9-other-{uuid.uuid4().hex[:6]}",
            ossie_root_path="projects/tempo_scan_impala",
            status="active",
        )
        session.add(other)
        session.commit()
        service = ChatAttachmentService(settings, session)
        with pytest.raises(ChatAttachmentServiceError):
            service.get_attachment(uuid.UUID(att_id), project_id=other.id)


def test_attachment_temp_rag_stream(attachment_client):
    client, _ = attachment_client
    phrase = f"M9UniqueEvidencePhrase{uuid.uuid4().hex[:10]}"
    upload = client.post(
        "/api/v1/chat/attachments/batch",
        data={"session_id": str(uuid.uuid4())},
        files=[("files", ("evidence.txt", io.BytesIO(f"{phrase} is documented in this attachment.".encode()), "text/plain"))],
    )
    att_id = upload.json()["accepted"][0]["id"]
    _wait_attachment(client, att_id)

    from unittest.mock import AsyncMock, patch
    from app.rag.models import RagLlmOutput

    async def _fake_llm(messages, response_model, **kwargs):
        return RagLlmOutput(
            grounding="SUPPORTED",
            direct_answer=f"Evidence mentions {phrase}.",
            executive_summary="Grounded.",
            cited_chunk_ids=[],
        )

    llm = AsyncMock()
    llm.generate_structured = _fake_llm

    with patch("app.services.rag_service.RAGService.rag_answer", autospec=True) as rag_answer:
        from app.services.rag_service import RagAnswerResult

        async def _fake_rag(self, **kwargs):
            assert kwargs.get("document_ids")
            return RagAnswerResult(
                grounding="SUPPORTED",
                answer_text=f"Evidence mentions {phrase}.",
                executive_summary="Grounded.",
                insights=[],
                caveats=[],
                business_implications=[],
                citations=[],
                retrieval_meta={"candidate_count": 1, "selected_count": 1},
                execution_metadata={"total_ms": 1},
                session_frame={},
                status="SUCCESS",
            )

        rag_answer.side_effect = _fake_rag
        response = client.post(
            "/chat/stream",
            json={
                "session_id": str(uuid.uuid4()),
                "question": f"What is {phrase}?",
                "provider": "qwen",
                "model": "qwen-model",
                "context_sources": [{"type": "uploaded_file", "id": att_id, "name": "evidence.txt"}],
            },
        )
    assert response.status_code == 200
    assert phrase in response.text
