"""Ask Data workspace settings and starter questions."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.ask_data.semantic_catalog_api import build_semantic_catalog_payload
from app.db.metadata_db import platform_metadata_configured
from app.projects.resolver import load_default_project
from app.db.platform_engine import get_session_factory
from app.db.platform_models import WorkspaceRow
from app.semantic_runtime.loader import SemanticRuntimeLoader
from app.workspace.ask_data_settings import (
    AskDataSettings,
    read_ask_data_settings,
    resolve_starters,
    resolve_starters_with_runtime,
    write_ask_data_settings,
)
from app.workspace.presentation_config_resolver import load_presentation_tier_config

router = APIRouter(prefix="/ask-data", tags=["ask-data"])


class AskDataFeedbackRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=64)
    session_id: str = Field(min_length=4, max_length=128)
    rating: str = Field(pattern="^(up|down)$")
    comment: str | None = Field(default=None, max_length=500)


def _require_platform_database_url(request: Request) -> str:
    settings = request.app.state.settings
    url = (settings.database_url or "").strip()
    if not platform_metadata_configured(settings):
        raise HTTPException(
            status_code=503,
            detail="Platform metadata requires DATABASE_URL (PostgreSQL or SQLite)",
        )
    return url


def _load_workspace(session, *, workspace_slug: str) -> WorkspaceRow:
    row = session.execute(
        select(WorkspaceRow).where(WorkspaceRow.slug == workspace_slug)
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail=f"Workspace not found: {workspace_slug}")
    return row


@router.get("/presentation-config")
def get_presentation_config(
    request: Request,
    workspace_slug: str = Query("default"),
) -> dict:
    """Effective Ask Data presentation tier config (deployment env + workspace overrides)."""
    settings_obj = request.app.state.settings
    workspace_id: str | None = None
    factory = None
    if platform_metadata_configured(settings_obj):
        url = (settings_obj.database_url or "").strip()
        if url:
            factory = get_session_factory(url)
            with factory() as session:
                workspace = _load_workspace(session, workspace_slug=workspace_slug)
                workspace_id = str(workspace.id)
    config = load_presentation_tier_config(
        settings_obj,
        session_factory=factory,
        workspace_id=workspace_id,
    )
    return {
        "workspace_slug": workspace_slug,
        "presentation": config.model_public(),
    }


@router.get("/semantic-catalog")
def get_semantic_catalog(
    request: Request,
    workspace_slug: str = Query("default"),
) -> dict:
    url = _require_platform_database_url(request)
    factory = get_session_factory(url)
    project = load_default_project(request.app.state.settings)
    if project is None:
        raise HTTPException(status_code=404, detail="Default project not seeded")
    with factory() as session:
        workspace = _load_workspace(session, workspace_slug=workspace_slug)
        payload = build_semantic_catalog_payload(
            session,
            workspace_id=workspace.id,
            project_id=project.id,
            settings_json=workspace.settings_json,
        )
    return {"workspace_slug": workspace_slug, **payload}


@router.post("/feedback")
def post_ask_data_feedback(body: AskDataFeedbackRequest, request: Request) -> dict:
    """Lightweight answer quality signal (stored as usage_events for analytics)."""
    from app.db.platform_models import UsageEventRow

    settings_obj = request.app.state.settings
    url = _require_platform_database_url(request)
    project = load_default_project(settings_obj)
    factory = get_session_factory(url)
    strategy = "ask_data_feedback_up" if body.rating == "up" else "ask_data_feedback_down"
    with factory() as session:
        session.add(
            UsageEventRow(
                workspace_id=project.workspace_id if project else None,
                project_id=project.id if project else None,
                request_id=body.request_id,
                session_id=body.session_id,
                provider="feedback",
                model=(body.comment or "")[:128],
                strategy=strategy,
                status="RECORDED",
                prompt_tokens=1 if body.rating == "up" else 0,
                completion_tokens=1 if body.rating == "down" else 0,
                total_tokens=1,
                llm_calls=0,
            )
        )
        session.commit()
    return {"ok": True}


@router.get("/starters")
def list_starters(
    request: Request,
    workspace_slug: str = Query("default"),
) -> dict:
    settings_obj = request.app.state.settings
    runtime_ctx = SemanticRuntimeLoader.get(settings_obj).get_bundle().context
    if not platform_metadata_configured(settings_obj):
        return resolve_starters_with_runtime(
            AskDataSettings(),
            runtime_ctx,
            deployment_settings=settings_obj,
        )

    url = _require_platform_database_url(request)
    factory = get_session_factory(url)
    with factory() as session:
        workspace = _load_workspace(session, workspace_slug=workspace_slug)
        settings = read_ask_data_settings(workspace.settings_json)
    return resolve_starters_with_runtime(
        settings,
        runtime_ctx,
        deployment_settings=settings_obj,
    )


@router.get("/settings")
def get_ask_data_settings(
    request: Request,
    workspace_slug: str = Query("default"),
) -> dict:
    url = _require_platform_database_url(request)
    factory = get_session_factory(url)
    with factory() as session:
        workspace = _load_workspace(session, workspace_slug=workspace_slug)
        settings = read_ask_data_settings(workspace.settings_json)
    return {"settings": settings.model_dump(), "workspace_slug": workspace_slug}


@router.put("/settings")
def put_ask_data_settings(
    body: AskDataSettings,
    request: Request,
    workspace_slug: str = Query("default"),
) -> dict:
    url = _require_platform_database_url(request)
    factory = get_session_factory(url)
    with factory() as session:
        workspace = _load_workspace(session, workspace_slug=workspace_slug)
        workspace.settings_json = write_ask_data_settings(workspace.settings_json, body)
        session.add(workspace)
        session.commit()
        session.refresh(workspace)
        settings = read_ask_data_settings(workspace.settings_json)
    return {"settings": settings.model_dump(), "workspace_slug": workspace_slug}
