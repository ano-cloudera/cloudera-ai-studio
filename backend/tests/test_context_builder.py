from __future__ import annotations

import uuid

from app.retrieval.context_builder import ContextBuilder
from app.retrieval.types import RetrievalCandidate


def _cand(text: str, idx: int) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        library_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        text=text,
        filename="f.txt",
        page_number=1,
        section=None,
        vector_score=1.0 - idx * 0.01,
    )


def test_context_budget_limits_selection():
    builder = ContextBuilder(max_context_tokens=50)
    ranked = [_cand("word " * 200, i) for i in range(5)]
    ctx = builder.build("q", ranked, total_candidates=5)
    assert ctx.selected_candidates >= 1
    assert ctx.token_budget_used <= 50
