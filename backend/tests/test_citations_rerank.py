from __future__ import annotations

import uuid

from app.rerank.provider import NoOpReranker
from app.retrieval.citations import candidate_to_citation
from app.retrieval.types import RetrievalCandidate


def _cand(**kwargs) -> RetrievalCandidate:
    base = dict(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        library_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        text="Evidence text about sell-in.",
        filename="brief.txt",
        page_number=None,
        section=None,
        vector_score=0.42,
    )
    base.update(kwargs)
    return RetrievalCandidate(**base)


def test_citation_uses_rerank_score_when_present():
    c = _cand(rerank_score=0.91)
    cite = candidate_to_citation(c)
    assert cite.score == 0.91
    assert cite.page_number is None
    assert "sell-in" in cite.snippet


def test_citation_does_not_fabricate_page_or_section():
    c = _cand(page_number=3, section="Metrics")
    cite = candidate_to_citation(c)
    assert cite.page_number == 3
    assert cite.section == "Metrics"


def test_noop_reranker_preserves_vector_scores():
    a = _cand(vector_score=0.9)
    b = _cand(vector_score=0.5)
    ranked = NoOpReranker().rerank("q", [b, a], top_n=2)
    assert ranked[0].vector_score == 0.9
    assert ranked[0].rerank_score == 0.9
    assert ranked[0].metadata.get("rerank_fallback") is True
