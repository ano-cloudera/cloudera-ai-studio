from __future__ import annotations

from app.retrieval.types import Citation, RetrievalCandidate


def candidate_to_citation(candidate: RetrievalCandidate, *, max_snippet_chars: int = 320) -> Citation:
    snippet = candidate.text.strip()
    if len(snippet) > max_snippet_chars:
        snippet = snippet[: max_snippet_chars - 1] + "…"
    score = candidate.rerank_score if candidate.rerank_score is not None else candidate.vector_score
    return Citation(
        document_id=candidate.document_id,
        filename=candidate.filename,
        page_number=candidate.page_number,
        section=candidate.section,
        chunk_id=candidate.chunk_id,
        source_uri=None,
        snippet=snippet,
        score=score,
    )
