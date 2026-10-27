from __future__ import annotations

import uuid

from pydantic import Field

from app.core.models import StrictModel


class RagQueryRequest(StrictModel):
    query: str = Field(min_length=1)
    project_id: uuid.UUID | None = None
    library_ids: list[uuid.UUID] | None = None
    conversation_id: str | None = Field(default=None, description="Maps to chat session_id")
    provider: str = "gemini"
    model: str = ""


class RagQueryResponse(StrictModel):
    route: str = "rag"
    status: str
    answer: str
    grounding: str | None = None
    citations: list[dict] = []
    retrieval: dict = {}
    execution_metadata: dict = {}
