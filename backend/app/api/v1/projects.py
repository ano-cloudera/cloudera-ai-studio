from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select

from app.db.platform_engine import get_session_factory
from app.db.platform_models import ProjectRow, WorkspaceRow
from app.projects.resolver import load_default_project

router = APIRouter(prefix="/projects", tags=["platform"])


def _require_postgres(request: Request) -> str:
    settings = request.app.state.settings
    url = (settings.database_url or "").strip()
    if settings.state_store.strip().lower() != "postgres" or not url:
        raise HTTPException(
            status_code=503,
            detail="Platform metadata requires STATE_STORE=postgres and DATABASE_URL",
        )
    return url


def _project_dict(row: ProjectRow) -> dict:
    return {
        "id": str(row.id),
        "workspace_id": str(row.workspace_id),
        "slug": row.slug,
        "name": row.name,
        "ossie_root_path": row.ossie_root_path,
        "status": row.status,
        "default_connector_id": str(row.default_connector_id) if row.default_connector_id else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("")
def list_projects(
    request: Request,
    workspace_slug: str = Query("default"),
) -> dict:
    url = _require_postgres(request)
    factory = get_session_factory(url)
    with factory() as session:
        workspace = session.execute(
            select(WorkspaceRow).where(WorkspaceRow.slug == workspace_slug)
        ).scalar_one_or_none()
        if not workspace:
            raise HTTPException(status_code=404, detail=f"Workspace not found: {workspace_slug}")
        rows = session.execute(
            select(ProjectRow)
            .where(ProjectRow.workspace_id == workspace.id)
            .order_by(ProjectRow.slug)
        ).scalars().all()
    return {"projects": [_project_dict(row) for row in rows]}


@router.get("/default")
def get_default_project(request: Request) -> dict:
    settings = request.app.state.settings
    _require_postgres(request)
    project = load_default_project(settings)
    if not project:
        raise HTTPException(status_code=404, detail="Default project not seeded")
    return {
        "project": {
            "id": str(project.id),
            "workspace_id": str(project.workspace_id),
            "slug": project.slug,
            "name": project.name,
            "ossie_root_path": project.ossie_root_path,
            "status": project.status,
            "default_connector_id": str(project.default_connector_id) if project.default_connector_id else None,
        }
    }
