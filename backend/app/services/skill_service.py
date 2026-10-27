from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.db.platform_models import SkillRow, SkillVersionRow
from app.skills.tool_registry import HANDLER_TYPES, ToolRegistry


class SkillServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass
class SkillCreate:
    name: str
    key: str
    scope: str
    description: str | None = None
    workspace_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    instructions: str = ""
    prompt_key: str | None = None
    input_schema: dict | None = None
    output_schema: dict | None = None
    allowed_tools: list[str] | None = None
    config: dict | None = None


@dataclass
class SkillVersionCreate:
    instructions: str
    prompt_key: str | None = None
    input_schema: dict | None = None
    output_schema: dict | None = None
    allowed_tools: list[str] | None = None
    config: dict | None = None


class SkillService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_skills(
        self,
        *,
        scope: str | None = None,
        workspace_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        search: str | None = None,
    ) -> list[SkillRow]:
        q = select(SkillRow).order_by(SkillRow.key, SkillRow.scope)
        if scope:
            q = q.where(SkillRow.scope == scope)
            if scope == "workspace" and workspace_id is not None:
                q = q.where(SkillRow.workspace_id == workspace_id, SkillRow.project_id.is_(None))
            elif scope == "project" and workspace_id is not None and project_id is not None:
                q = q.where(SkillRow.workspace_id == workspace_id, SkillRow.project_id == project_id)
        elif workspace_id is not None and project_id is not None:
            q = q.where(
                or_(
                    and_(
                        SkillRow.scope == "workspace",
                        SkillRow.workspace_id == workspace_id,
                        SkillRow.project_id.is_(None),
                    ),
                    and_(
                        SkillRow.scope == "project",
                        SkillRow.workspace_id == workspace_id,
                        SkillRow.project_id == project_id,
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

    def get_skill(self, skill_id: uuid.UUID) -> SkillRow:
        row = self._session.get(SkillRow, skill_id)
        if not row:
            raise SkillServiceError("not_found", "Skill not found", 404)
        return row

    def create_skill(self, body: SkillCreate) -> SkillRow:
        self._validate_scope(body.scope, body.workspace_id, body.project_id)
        if self._find_skill_row(body.key, body.scope, body.workspace_id, body.project_id):
            raise SkillServiceError("duplicate", "Skill key already exists for this scope", 409)
        row = SkillRow(
            name=body.name.strip(),
            key=body.key.strip(),
            scope=body.scope,
            description=(body.description or "").strip() or None,
            workspace_id=body.workspace_id,  # type: ignore[arg-type]
            project_id=body.project_id,
            status="active",
        )
        self._session.add(row)
        self._session.flush()
        self.create_version(
            skill_id=row.id,
            body=SkillVersionCreate(
                instructions=body.instructions or "",
                prompt_key=body.prompt_key,
                input_schema=body.input_schema,
                output_schema=body.output_schema,
                allowed_tools=body.allowed_tools or [],
                config=body.config or {"handler_type": "prompt_only"},
            ),
            as_draft=True,
        )
        self._session.refresh(row)
        return row

    def create_version(
        self,
        *,
        skill_id: uuid.UUID,
        body: SkillVersionCreate,
        as_draft: bool = True,
    ) -> SkillVersionRow:
        skill = self.get_skill(skill_id)
        config = dict(body.config or {})
        handler_type = str(config.get("handler_type") or "prompt_only")
        allowed = list(body.allowed_tools or [])
        try:
            ToolRegistry.validate_handler_tools(handler_type, allowed)
        except ValueError as exc:
            raise SkillServiceError("invalid_tools", str(exc), 422) from exc
        if handler_type not in HANDLER_TYPES:
            raise SkillServiceError("invalid_handler", f"handler_type must be one of {sorted(HANDLER_TYPES)}", 422)

        next_num = (
            self._session.scalar(
                select(func.coalesce(func.max(SkillVersionRow.version_number), 0)).where(
                    SkillVersionRow.skill_id == skill_id
                )
            )
            or 0
        ) + 1
        version = SkillVersionRow(
            skill_id=skill_id,
            version_number=int(next_num),
            instructions=body.instructions or "",
            prompt_key=(body.prompt_key or "").strip() or None,
            input_schema=body.input_schema,
            output_schema=body.output_schema,
            allowed_tools=allowed,
            config={**config, "handler_type": handler_type},
            status="DRAFT" if as_draft else "ACTIVE",
        )
        self._session.add(version)
        self._session.flush()
        if not as_draft:
            self._activate_version(skill, version)
        self._session.refresh(version)
        return version

    def list_versions(self, skill_id: uuid.UUID) -> list[SkillVersionRow]:
        self.get_skill(skill_id)
        return list(
            self._session.execute(
                select(SkillVersionRow)
                .where(SkillVersionRow.skill_id == skill_id)
                .order_by(SkillVersionRow.version_number.desc())
            )
            .scalars()
            .all()
        )

    def publish_version(self, skill_id: uuid.UUID, version_id: uuid.UUID) -> SkillVersionRow:
        skill = self.get_skill(skill_id)
        version = self._session.get(SkillVersionRow, version_id)
        if not version or version.skill_id != skill_id:
            raise SkillServiceError("not_found", "Version not found", 404)
        if version.status == "ACTIVE":
            return version
        self._activate_version(skill, version)
        self._session.refresh(version)
        return version

    def rollback(self, skill_id: uuid.UUID, version_id: uuid.UUID) -> SkillVersionRow:
        return self.publish_version(skill_id, version_id)

    def get_active_version(self, skill_id: uuid.UUID) -> SkillVersionRow:
        skill = self.get_skill(skill_id)
        if not skill.active_version_id:
            raise SkillServiceError("no_active_version", "Skill has no published active version", 409)
        version = self._session.get(SkillVersionRow, skill.active_version_id)
        if not version or version.status != "ACTIVE":
            raise SkillServiceError("no_active_version", "Skill has no published active version", 409)
        return version

    def resolve_active(
        self,
        *,
        skill_key: str,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID | None,
    ) -> tuple[SkillRow, SkillVersionRow, str] | None:
        for scope, proj in (("project", project_id), ("workspace", None)):
            if scope == "project" and not project_id:
                continue
            row = self._find_skill_row(skill_key, scope, workspace_id, proj)
            if not row or not row.active_version_id:
                continue
            version = self._session.get(SkillVersionRow, row.active_version_id)
            if version and version.status == "ACTIVE":
                return row, version, scope
        return None

    def _activate_version(self, skill: SkillRow, version: SkillVersionRow) -> None:
        active_rows = self._session.execute(
            select(SkillVersionRow).where(
                SkillVersionRow.skill_id == skill.id,
                SkillVersionRow.status == "ACTIVE",
            )
        ).scalars().all()
        for row in active_rows:
            if row.id != version.id:
                row.status = "ARCHIVED"
        version.status = "ACTIVE"
        skill.active_version_id = version.id
        self._session.flush()

    def _find_skill_row(
        self,
        key: str,
        scope: str,
        workspace_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
    ) -> SkillRow | None:
        q = select(SkillRow).where(SkillRow.key == key, SkillRow.scope == scope)
        if scope == "workspace":
            q = q.where(SkillRow.workspace_id == workspace_id, SkillRow.project_id.is_(None))
        else:
            q = q.where(SkillRow.project_id == project_id, SkillRow.workspace_id == workspace_id)
        return self._session.execute(q).scalar_one_or_none()

    @staticmethod
    def _validate_scope(scope: str, workspace_id: uuid.UUID | None, project_id: uuid.UUID | None) -> None:
        if scope not in {"workspace", "project"}:
            raise SkillServiceError("invalid_scope", "scope must be workspace or project", 422)
        if not workspace_id:
            raise SkillServiceError("invalid_scope", "workspace_id is required", 422)
        if scope == "workspace" and project_id:
            raise SkillServiceError("invalid_scope", "workspace skills cannot have project_id", 422)
        if scope == "project" and not project_id:
            raise SkillServiceError("invalid_scope", "project skills require project_id", 422)
