"""Idempotent seed for default workspace + example OSSIE project."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.platform_models import ProjectRow, WorkspaceRow
from app.projects.types import ProjectRecord, WorkspaceRecord

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_SLUG = "default"
DEFAULT_PROJECT_SLUG = "tempo_scan_impala"
DEFAULT_PROJECT_NAME = "Tempo Scan (reference)"


def ensure_platform_seed(
    session: Session,
    *,
    backend_root: Path,
    project_slug: str = DEFAULT_PROJECT_SLUG,
    ossie_relative_path: str | None = None,
) -> tuple[WorkspaceRecord, ProjectRecord]:
    ossie_path = ossie_relative_path or f"projects/{project_slug}"
    workspace = session.execute(
        select(WorkspaceRow).where(WorkspaceRow.slug == DEFAULT_WORKSPACE_SLUG)
    ).scalar_one_or_none()
    if not workspace:
        workspace = WorkspaceRow(slug=DEFAULT_WORKSPACE_SLUG, name="Default Workspace", settings_json={})
        session.add(workspace)
        session.flush()
        logger.info("platform_seed created workspace slug=%s", DEFAULT_WORKSPACE_SLUG)

    project = session.execute(
        select(ProjectRow).where(
            ProjectRow.workspace_id == workspace.id,
            ProjectRow.slug == project_slug,
        )
    ).scalar_one_or_none()
    if not project:
        resolved = (backend_root / ossie_path).resolve()
        if not resolved.is_dir():
            logger.warning("platform_seed ossie path missing: %s", resolved)
        project = ProjectRow(
            workspace_id=workspace.id,
            slug=project_slug,
            name=DEFAULT_PROJECT_NAME,
            ossie_root_path=ossie_path,
            status="active",
        )
        session.add(project)
        session.flush()
        logger.info("platform_seed created project slug=%s path=%s", project_slug, ossie_path)

    session.commit()
    return (
        WorkspaceRecord(id=workspace.id, slug=workspace.slug, name=workspace.name),
        ProjectRecord(
            id=project.id,
            workspace_id=project.workspace_id,
            slug=project.slug,
            name=project.name,
            ossie_root_path=project.ossie_root_path,
            status=project.status,
            default_connector_id=project.default_connector_id,
        ),
    )
