from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.db.platform_engine import get_session_factory
from app.db.platform_models import WorkspaceRow

router = APIRouter(prefix="/workspaces", tags=["platform"])


def _require_platform_database_url(request: Request) -> str:
    from app.db.metadata_db import platform_metadata_configured

    settings = request.app.state.settings
    url = (settings.database_url or "").strip()
    if not platform_metadata_configured(settings):
        raise HTTPException(
            status_code=503,
            detail="Platform metadata requires DATABASE_URL (PostgreSQL or SQLite)",
        )
    return url


def _workspace_dict(row: WorkspaceRow) -> dict:
    return {
        "id": str(row.id),
        "slug": row.slug,
        "name": row.name,
        "settings": row.settings_json or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("")
def list_workspaces(request: Request) -> dict:
    url = _require_platform_database_url(request)
    factory = get_session_factory(url)
    with factory() as session:
        rows = session.execute(select(WorkspaceRow).order_by(WorkspaceRow.slug)).scalars().all()
    return {"workspaces": [_workspace_dict(row) for row in rows]}


@router.get("/default")
def get_default_workspace(request: Request) -> dict:
    url = _require_platform_database_url(request)
    factory = get_session_factory(url)
    with factory() as session:
        row = session.execute(
            select(WorkspaceRow).where(WorkspaceRow.slug == "default")
        ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Default workspace not seeded")
    return {"workspace": _workspace_dict(row)}
