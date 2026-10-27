from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.db.platform_models import SkillRow, SkillVersionRow
from app.services.skill_service import SkillService
from app.skills.types import ResolvedSkill


class SkillResolver:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._svc = SkillService(session)

    def resolve(
        self,
        skill_key: str,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID | None,
    ) -> ResolvedSkill | None:
        effective = self._svc.resolve_active(skill_key=skill_key, workspace_id=workspace_id, project_id=project_id)
        if not effective:
            return None
        skill, version, source = effective
        chain = ["project", "workspace"]
        idx = chain.index(source) if source in chain else 0
        return ResolvedSkill(skill=skill, version=version, source=source, chain=chain[: idx + 1])

    def resolve_by_id(self, skill_id: uuid.UUID) -> ResolvedSkill | None:
        skill = self._session.get(SkillRow, skill_id)
        if not skill or not skill.active_version_id:
            return None
        version = self._session.get(SkillVersionRow, skill.active_version_id)
        if not version or version.status != "ACTIVE":
            return None
        source = "project" if skill.scope == "project" else "workspace"
        return ResolvedSkill(skill=skill, version=version, source=source, chain=[source])
