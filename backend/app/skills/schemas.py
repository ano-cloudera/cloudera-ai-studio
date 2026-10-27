from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.core.models import StrictModel


class SkillCreateRequest(StrictModel):
    name: str = Field(min_length=1, max_length=256)
    key: str = Field(min_length=1, max_length=128)
    scope: str = Field(pattern="^(workspace|project)$")
    description: str | None = None
    workspace_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    instructions: str = ""
    prompt_key: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    allowed_tools: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=lambda: {"handler_type": "prompt_only"})


class SkillVersionCreateRequest(StrictModel):
    instructions: str = ""
    prompt_key: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    allowed_tools: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=lambda: {"handler_type": "prompt_only"})


class SkillExecuteRequest(StrictModel):
    input: str = Field(min_length=1)
    conversation_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class SkillResponse(StrictModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID | None
    name: str
    key: str
    scope: str
    description: str | None
    status: str
    active_version_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class SkillVersionResponse(StrictModel):
    id: uuid.UUID
    skill_id: uuid.UUID
    version_number: int
    instructions: str
    prompt_key: str | None
    input_schema: dict[str, Any] | None
    output_schema: dict[str, Any] | None
    allowed_tools: list[str]
    config: dict[str, Any]
    status: str
    created_at: datetime
