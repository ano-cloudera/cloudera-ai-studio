from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChatAttachmentResponse(StrictModel):
    id: uuid.UUID
    session_id: str
    filename: str
    display_name: str
    mime_type: str
    size_bytes: int
    status: str
    processing_type: str
    error_code: str | None = None
    error_message: str | None = None
    document_id: uuid.UUID | None = None
    chunk_count: int | None = None
    page_count: int | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime


class BatchUploadResponse(StrictModel):
    requested: int
    accepted: list[ChatAttachmentResponse]
    rejected: list[dict[str, Any]]


class SaveAttachmentToKnowledgeRequest(StrictModel):
    library_id: uuid.UUID | None = None
    new_library_name: str | None = None
