from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.rag.models import RagLlmOutput
from app.services.rag_service import RAGService


class _FakeRetrieval:
    def retrieve(self, **kwargs):
        cid = uuid.uuid4()
        return {
            "results": [
                {
                    "chunk_id": str(cid),
                    "document_id": str(uuid.uuid4()),
                    "library_id": str(kwargs["library_ids"][0]),
                    "workspace_id": str(kwargs["workspace_id"]),
                    "project_id": str(kwargs["project_id"]),
                    "text": "alpha-one sell-in metric policy",
                    "filename": "policy.txt",
                    "page_number": 2,
                    "section": None,
                    "vector_score": 0.88,
                    "rerank_score": 0.91,
                    "metadata": {},
                }
            ],
            "context": {"total_candidates": 3, "selected_candidates": 1, "token_budget_used": 100},
            "metadata": {"total_retrieval_ms": 5, "embedding_ms": 1, "vector_search_ms": 2, "rerank_ms": 1},
        }


@pytest.mark.asyncio
async def test_rag_service_grounded_answer():
    settings = Settings(_env_file=None)
    llm = AsyncMock()
    cid_holder: list[str] = []

    async def _gen(messages, response_model, **kwargs):
        text = messages[-1]["content"]
        chunk_id = text.split("chunk_id=")[1].split()[0]
        cid_holder.append(chunk_id)
        return RagLlmOutput(
            grounding="SUPPORTED",
            direct_answer="The policy covers sell-in alpha-one.",
            executive_summary="Sell-in alpha-one is documented.",
            cited_chunk_ids=[chunk_id],
        )

    llm.generate_structured = _gen
    session = MagicMock()
    service = RAGService(settings, retrieval=_FakeRetrieval())  # type: ignore[arg-type]
    lib = uuid.uuid4()
    with patch("app.services.rag_service.resolve_library_ids", return_value=[lib]):
        result = await service.rag_answer(
            session=session,
            query="sell-in alpha-one",
            workspace_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            library_ids=[str(lib)],
            conversation_history=[],
            llm_provider=llm,
        )
    assert result.grounding == "SUPPORTED"
    assert result.citations
    assert str(result.citations[0].chunk_id) == cid_holder[0]


@pytest.mark.asyncio
async def test_rag_service_no_library_scope():
    settings = Settings(_env_file=None)
    session = MagicMock()
    service = RAGService(settings, retrieval=_FakeRetrieval())  # type: ignore[arg-type]
    result = await service.rag_answer(
        session=session,
        query="anything",
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        library_ids=None,
        conversation_history=[],
        llm_provider=AsyncMock(),
    )
    assert result.grounding == "INSUFFICIENT_EVIDENCE"
    assert result.status == "NO_DATA"
