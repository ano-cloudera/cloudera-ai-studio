from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.core.models import StrictModel


class PromptCreateRequest(StrictModel):
    name: str = Field(min_length=1, max_length=256)
    key: str = Field(min_length=1, max_length=128)
    scope: str = Field(pattern="^(global|workspace|project)$")
    description: str | None = None
    workspace_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    initial_content: str | None = None


class PromptVersionCreateRequest(StrictModel):
    content: str = Field(min_length=1)
    created_by: str | None = None


class PromptResolveRequest(StrictModel):
    prompt_key: str
    project_id: uuid.UUID | None = None


class PromptResponse(StrictModel):
    id: uuid.UUID
    workspace_id: uuid.UUID | None
    project_id: uuid.UUID | None
    name: str
    key: str
    scope: str
    description: str | None
    active_version_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class PromptVersionResponse(StrictModel):
    id: uuid.UUID
    prompt_id: uuid.UUID
    version_number: int
    content: str
    status: str
    created_by: str | None
    created_at: datetime
