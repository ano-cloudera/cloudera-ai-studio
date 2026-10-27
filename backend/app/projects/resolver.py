from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import select

from app.core.config import Settings, BACKEND_ROOT
from app.db.platform_engine import get_session_factory
from app.db.platform_models import ProjectRow, WorkspaceRow
from app.projects.types import ProjectRecord

logger = logging.getLogger(__name__)


def _resolve_ossie_path(settings: Settings, relative_or_absolute: str) -> Path:
    path = Path(relative_or_absolute)
    if path.is_absolute():
        return path
    return (BACKEND_ROOT / path).resolve()


def resolve_ossie_project_dir(settings: Settings) -> Path:
    """Active OSSIE project directory for semantic layer."""
    legacy = (settings.project_root / settings.ossie_project_id).resolve()
    if settings.state_store.strip().lower() != "postgres" or not (settings.database_url or "").strip():
        return legacy
    try:
        project = load_default_project(settings)
        if project:
            candidate = _resolve_ossie_path(settings, project.ossie_root_path)
            if candidate.is_dir():
                return candidate
            logger.warning("project ossie path missing %s — fallback legacy", candidate)
    except Exception as exc:
        logger.warning("project resolver postgres failed: %s — fallback legacy", type(exc).__name__)
    return legacy


def load_default_project(settings: Settings) -> ProjectRecord | None:
    url = (settings.database_url or "").strip()
    if not url:
        return None
    factory = get_session_factory(url)
    with factory() as session:
        workspace = session.execute(
            select(WorkspaceRow).where(WorkspaceRow.slug == "default")
        ).scalar_one_or_none()
        if not workspace:
            return None
        slug = settings.default_project_slug or settings.ossie_project_id
        project = session.execute(
            select(ProjectRow).where(
                ProjectRow.workspace_id == workspace.id,
                ProjectRow.slug == slug,
                ProjectRow.status == "active",
            )
        ).scalar_one_or_none()
        if not project:
            return None
        return ProjectRecord(
            id=project.id,
            workspace_id=project.workspace_id,
            slug=project.slug,
            name=project.name,
            ossie_root_path=project.ossie_root_path,
            status=project.status,
            default_connector_id=project.default_connector_id,
        )


def get_default_project_ids(settings: Settings) -> tuple | None:
    project = load_default_project(settings)
    if not project:
        return None
    return (project.workspace_id, project.id)
