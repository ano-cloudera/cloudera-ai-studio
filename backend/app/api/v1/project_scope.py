from __future__ import annotations

import uuid

from app.db.platform_models import LibraryRow, PromptRow, SkillRow
from app.services.document_service import DocumentServiceError
from app.services.library_service import LibraryServiceError
from app.services.prompt_service import PromptServiceError
from app.services.skill_service import SkillServiceError


def assert_library_scope(row: LibraryRow, *, workspace_id: uuid.UUID, project_id: uuid.UUID) -> None:
    if row.workspace_id != workspace_id or row.project_id != project_id:
        raise LibraryServiceError("not_found", "Library not found", 404)


def assert_prompt_scope(row: PromptRow, *, workspace_id: uuid.UUID, project_id: uuid.UUID) -> None:
    if row.scope == "global":
        return
    if row.scope == "workspace":
        if row.workspace_id == workspace_id:
            return
    elif row.scope == "project":
        if row.workspace_id == workspace_id and row.project_id == project_id:
            return
    raise PromptServiceError("not_found", "Prompt not found", 404)


def assert_skill_scope(row: SkillRow, *, workspace_id: uuid.UUID, project_id: uuid.UUID) -> None:
    if row.scope == "global":
        return
    if row.scope == "workspace":
        if row.workspace_id == workspace_id:
            return
    elif row.scope == "project":
        if row.workspace_id == workspace_id and row.project_id == project_id:
            return
    raise SkillServiceError("not_found", "Skill not found", 404)


def assert_document_scope(row, *, project_id: uuid.UUID) -> None:
    if row.project_id != project_id:
        raise DocumentServiceError("not_found", "Document not found", 404)


def load_prompt_in_context(svc, prompt_id: uuid.UUID, *, workspace_id: uuid.UUID, project_id: uuid.UUID) -> PromptRow:
    row = svc.get_prompt(prompt_id)
    assert_prompt_scope(row, workspace_id=workspace_id, project_id=project_id)
    return row


def load_skill_in_context(svc, skill_id: uuid.UUID, *, workspace_id: uuid.UUID, project_id: uuid.UUID) -> SkillRow:
    row = svc.get_skill(skill_id)
    assert_skill_scope(row, workspace_id=workspace_id, project_id=project_id)
    return row
