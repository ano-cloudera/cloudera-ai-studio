from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.db.platform_models import PromptRow, PromptVersionRow
from app.prompt_management.types import EffectivePrompt


class PromptServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass
class PromptCreate:
    name: str
    key: str
    scope: str
    description: str | None = None
    workspace_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    initial_content: str | None = None
    created_by: str | None = None


class PromptService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_prompts(
        self,
        *,
        scope: str | None = None,
        workspace_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        search: str | None = None,
    ) -> list[PromptRow]:
        q = select(PromptRow).order_by(PromptRow.key, PromptRow.scope)
        if scope:
            q = q.where(PromptRow.scope == scope)
            if scope == "global":
                q = q.where(PromptRow.workspace_id.is_(None), PromptRow.project_id.is_(None))
            elif scope == "workspace" and workspace_id is not None:
                q = q.where(PromptRow.workspace_id == workspace_id, PromptRow.project_id.is_(None))
            elif scope == "project" and workspace_id is not None and project_id is not None:
                q = q.where(PromptRow.workspace_id == workspace_id, PromptRow.project_id == project_id)
        elif workspace_id is not None and project_id is not None:
            q = q.where(
                or_(
                    and_(PromptRow.scope == "global", PromptRow.workspace_id.is_(None), PromptRow.project_id.is_(None)),
                    and_(
                        PromptRow.scope == "workspace",
                        PromptRow.workspace_id == workspace_id,
                        PromptRow.project_id.is_(None),
                    ),
                    and_(
                        PromptRow.scope == "project",
                        PromptRow.workspace_id == workspace_id,
                        PromptRow.project_id == project_id,
                    ),
                )
            )
        rows = self._session.execute(q).scalars().all()
        if search:
            needle = search.strip().lower()
            rows = [
                r
                for r in rows
                if needle in r.name.lower() or needle in r.key.lower() or (r.description or "").lower().find(needle) >= 0
            ]
        return list(rows)

    def get_prompt(self, prompt_id: uuid.UUID) -> PromptRow:
        row = self._session.get(PromptRow, prompt_id)
        if not row:
            raise PromptServiceError("not_found", "Prompt not found", 404)
        return row

    def create_prompt(self, body: PromptCreate) -> PromptRow:
        self._validate_scope(body.scope, body.workspace_id, body.project_id)
        if self._find_prompt_row(body.key, body.scope, body.workspace_id, body.project_id):
            raise PromptServiceError("duplicate", "Prompt key already exists for this scope", 409)
        row = PromptRow(
            name=body.name.strip(),
            key=body.key.strip(),
            scope=body.scope,
            description=(body.description or "").strip() or None,
            workspace_id=body.workspace_id,
            project_id=body.project_id,
        )
        self._session.add(row)
        self._session.flush()
        content = (body.initial_content or "").strip() or f"# {body.name}\n"
        self.create_version(prompt_id=row.id, content=content, created_by=body.created_by, as_draft=True)
        self._session.refresh(row)
        return row

    def create_version(
        self,
        *,
        prompt_id: uuid.UUID,
        content: str,
        created_by: str | None = None,
        as_draft: bool = True,
    ) -> PromptVersionRow:
        prompt = self.get_prompt(prompt_id)
        next_num = (
            self._session.scalar(
                select(func.coalesce(func.max(PromptVersionRow.version_number), 0)).where(
                    PromptVersionRow.prompt_id == prompt_id
                )
            )
            or 0
        ) + 1
        version = PromptVersionRow(
            prompt_id=prompt_id,
            version_number=int(next_num),
            content=content,
            status="DRAFT" if as_draft else "ACTIVE",
            created_by=created_by,
        )
        self._session.add(version)
        self._session.flush()
        if not as_draft:
            self._activate_version(prompt, version)
        self._session.refresh(version)
        return version

    def list_versions(self, prompt_id: uuid.UUID) -> list[PromptVersionRow]:
        self.get_prompt(prompt_id)
        return list(
            self._session.execute(
                select(PromptVersionRow)
                .where(PromptVersionRow.prompt_id == prompt_id)
                .order_by(PromptVersionRow.version_number.desc())
            )
            .scalars()
            .all()
        )

    def publish_version(self, prompt_id: uuid.UUID, version_id: uuid.UUID) -> PromptVersionRow:
        prompt = self.get_prompt(prompt_id)
        version = self._session.get(PromptVersionRow, version_id)
        if not version or version.prompt_id != prompt_id:
            raise PromptServiceError("not_found", "Version not found", 404)
        if version.status == "ACTIVE":
            return version
        self._activate_version(prompt, version)
        self._session.refresh(version)
        return version

    def rollback(self, prompt_id: uuid.UUID, version_id: uuid.UUID) -> PromptVersionRow:
        return self.publish_version(prompt_id, version_id)

    def _activate_version(self, prompt: PromptRow, version: PromptVersionRow) -> None:
        active_rows = self._session.execute(
            select(PromptVersionRow).where(
                PromptVersionRow.prompt_id == prompt.id,
                PromptVersionRow.status == "ACTIVE",
            )
        ).scalars().all()
        for row in active_rows:
            if row.id != version.id:
                row.status = "ARCHIVED"
        version.status = "ACTIVE"
        prompt.active_version_id = version.id
        self._session.flush()

    def resolve_effective(
        self,
        *,
        prompt_key: str,
        workspace_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
    ) -> EffectivePrompt:
        chain: list[str] = []
        for scope, ws, proj in (
            ("project", workspace_id, project_id),
            ("workspace", workspace_id, None),
            ("global", None, None),
        ):
            if scope == "project" and not project_id:
                continue
            if scope == "workspace" and not workspace_id:
                continue
            row = self._find_prompt_row(prompt_key, scope, ws, proj)
            if not row or not row.active_version_id:
                continue
            version = self._session.get(PromptVersionRow, row.active_version_id)
            if version and version.status == "ACTIVE" and version.content.strip():
                chain.append(scope)
                return EffectivePrompt(
                    prompt_key=prompt_key,
                    content=version.content,
                    source=scope,
                    chain=[*chain],
                )
        return EffectivePrompt(prompt_key=prompt_key, content="", source="file", chain=[])

    def _find_prompt_row(
        self,
        key: str,
        scope: str,
        workspace_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
    ) -> PromptRow | None:
        q = select(PromptRow).where(PromptRow.key == key, PromptRow.scope == scope)
        if scope == "global":
            q = q.where(PromptRow.workspace_id.is_(None), PromptRow.project_id.is_(None))
        elif scope == "workspace":
            q = q.where(PromptRow.workspace_id == workspace_id, PromptRow.project_id.is_(None))
        else:
            q = q.where(PromptRow.project_id == project_id, PromptRow.workspace_id == workspace_id)
        return self._session.execute(q).scalar_one_or_none()

    @staticmethod
    def _validate_scope(scope: str, workspace_id: uuid.UUID | None, project_id: uuid.UUID | None) -> None:
        if scope not in {"global", "workspace", "project"}:
            raise PromptServiceError("invalid_scope", "scope must be global, workspace, or project", 422)
        if scope == "global" and (workspace_id or project_id):
            raise PromptServiceError("invalid_scope", "global prompts cannot have workspace/project ids", 422)
        if scope == "workspace" and (not workspace_id or project_id):
            raise PromptServiceError("invalid_scope", "workspace prompts require workspace_id", 422)
        if scope == "project" and (not workspace_id or not project_id):
            raise PromptServiceError("invalid_scope", "project prompts require workspace and project ids", 422)
