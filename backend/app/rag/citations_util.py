from __future__ import annotations

import uuid

from app.core.models import CitationRecord
from app.retrieval.citations import candidate_to_citation
from app.retrieval.types import Citation, RetrievalCandidate


def dedupe_citations(citations: list[Citation]) -> list[Citation]:
    seen: set[str] = set()
    out: list[Citation] = []
    for cite in citations:
        key = str(cite.chunk_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(cite)
    return out


def citations_from_evidence(
    evidence: list[RetrievalCandidate],
    *,
    cited_chunk_ids: set[str] | None = None,
) -> list[Citation]:
    selected = evidence
    if cited_chunk_ids is not None:
        selected = [c for c in evidence if str(c.chunk_id) in cited_chunk_ids]
        if not selected and evidence:
            selected = evidence[:1]
    cites = [candidate_to_citation(c) for c in selected]
    return dedupe_citations(cites)


def citation_records(citations: list[Citation]) -> list[CitationRecord]:
    out: list[CitationRecord] = []
    for cite in citations:
        out.append(
            CitationRecord(
                document_id=str(cite.document_id),
                filename=cite.filename,
                page_number=cite.page_number,
                section=cite.section,
                chunk_id=str(cite.chunk_id),
                source_uri=cite.source_uri,
                snippet=cite.snippet,
                score=cite.score,
            )
        )
    return out


def validate_cited_ids(cited_chunk_ids: list[str], evidence: list[RetrievalCandidate]) -> set[str]:
    allowed = {str(c.chunk_id) for c in evidence}
    return {cid for cid in cited_chunk_ids if cid in allowed}
