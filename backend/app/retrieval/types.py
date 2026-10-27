from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RetrievalCandidate:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    library_id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    text: str
    filename: str | None
    page_number: int | None
    section: str | None
    vector_score: float
    rerank_score: float | None = None
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Citation:
    document_id: uuid.UUID
    filename: str | None
    page_number: int | None
    section: str | None
    chunk_id: uuid.UUID
    source_uri: str | None
    snippet: str
    score: float


@dataclass(frozen=True)
class RetrievedContext:
    query: str
    evidence: list[RetrievalCandidate]
    citations: list[Citation]
    total_candidates: int
    selected_candidates: int
    token_budget_used: int
