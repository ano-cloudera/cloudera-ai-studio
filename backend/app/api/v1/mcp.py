from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select

from app.db.metadata_db import platform_metadata_configured
from app.db.platform_engine import get_session_factory
from app.db.platform_models import WorkspaceRow
from app.mcp.registry import connectors_payload
from app.mcp.client import probe_mcp_server
from app.workspace.mcp_settings import McpServerEntry, McpWorkspaceSettings, read_mcp_settings, write_mcp_settings

router = APIRouter(prefix="/mcp", tags=["mcp"])


def _require_platform_database_url(request: Request) -> str:
    settings = request.app.state.settings
    if not platform_metadata_configured(settings):
        raise HTTPException(
            status_code=503,
            detail="Platform metadata requires DATABASE_URL (PostgreSQL or SQLite)",
        )
    return (settings.database_url or "").strip()


def _load_workspace(session, *, workspace_slug: str) -> WorkspaceRow:
    row = session.execute(select(WorkspaceRow).where(WorkspaceRow.slug == workspace_slug)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail=f"Workspace not found: {workspace_slug}")
    return row


@router.get("/settings")
def get_mcp_settings(
    request: Request,
    workspace_slug: str = Query("default"),
) -> dict:
    url = _require_platform_database_url(request)
    factory = get_session_factory(url)
    with factory() as session:
        workspace = _load_workspace(session, workspace_slug=workspace_slug)
        settings = read_mcp_settings(workspace.settings_json)
    return {"settings": settings.model_dump(), "workspace_slug": workspace_slug}


@router.put("/settings")
def put_mcp_settings(
    body: McpWorkspaceSettings,
    request: Request,
    workspace_slug: str = Query("default"),
) -> dict:
    url = _require_platform_database_url(request)
    factory = get_session_factory(url)
    with factory() as session:
        workspace = _load_workspace(session, workspace_slug=workspace_slug)
        workspace.settings_json = write_mcp_settings(workspace.settings_json, body)
        session.add(workspace)
        session.commit()
        session.refresh(workspace)
        settings = read_mcp_settings(workspace.settings_json)
    return {"settings": settings.model_dump(), "workspace_slug": workspace_slug}


@router.post("/test-connection")
async def test_mcp_connection(body: McpServerEntry) -> dict:
    return await probe_mcp_server(body)


@router.get("/connectors")
def list_mcp_connectors(
    request: Request,
    workspace_slug: str = Query("default"),
) -> dict:
    deployment = request.app.state.settings
    url = _require_platform_database_url(request)
    factory = get_session_factory(url)
    with factory() as session:
        workspace = _load_workspace(session, workspace_slug=workspace_slug)
        payload = connectors_payload(deployment, workspace_settings_json=workspace.settings_json)
    return {"connectors": payload, "workspace_slug": workspace_slug}
