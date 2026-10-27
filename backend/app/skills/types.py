from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.db.platform_models import SkillRow, SkillVersionRow
from app.prompt_management.types import EffectivePrompt


@dataclass
class ResolvedSkill:
    skill: SkillRow
    version: SkillVersionRow
    source: str
    chain: list[str] = field(default_factory=list)


@dataclass
class SkillExecutionContext:
    skill: SkillRow
    version: SkillVersionRow
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    user_input: str
    conversation_id: str | None
    resolved_prompt: EffectivePrompt | None
    allowed_tools: list[str]
    handler_type: str
    runtime_metadata: dict[str, Any] = field(default_factory=dict)
