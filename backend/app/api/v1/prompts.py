from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import default_project_context, postgres_session, require_postgres_settings
from app.api.v1.project_scope import assert_prompt_scope, load_prompt_in_context
from app.core.config import Settings
from app.prompt_management.resolver import PromptResolver
from app.prompt_management.schemas import (
    PromptCreateRequest,
    PromptResolveRequest,
    PromptResponse,
    PromptVersionCreateRequest,
    PromptVersionResponse,
)
from app.db.platform_models import PromptVersionRow
from app.services.prompt_service import PromptCreate, PromptService, PromptServiceError

router = APIRouter(prefix="/prompts", tags=["prompts"])


def _err(exc: PromptServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


def _prompt_row(row) -> dict:
    return PromptResponse(
        id=row.id,
        workspace_id=row.workspace_id,
        project_id=row.project_id,
        name=row.name,
        key=row.key,
        scope=row.scope,
        description=row.description,
        active_version_id=row.active_version_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    ).model_dump(mode="json")


def _version_row(row) -> dict:
    return PromptVersionResponse(
        id=row.id,
        prompt_id=row.prompt_id,
        version_number=row.version_number,
        content=row.content,
        status=row.status,
        created_by=row.created_by,
        created_at=row.created_at,
    ).model_dump(mode="json")


@router.get("")
def list_prompts(
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
    scope: str | None = Query(None),
    search: str | None = Query(None),
    project_id: uuid.UUID | None = Query(None),
) -> dict:
    workspace_id, default_project_id = ctx
    svc = PromptService(session)
    rows = svc.list_prompts(
        scope=scope,
        workspace_id=workspace_id,
        project_id=project_id or default_project_id if scope == "project" else project_id,
        search=search,
    )
    return {"prompts": [_prompt_row(r) for r in rows]}


@router.post("")
def create_prompt(
    body: PromptCreateRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
) -> dict:
    workspace_id, default_project_id = ctx
    ws = body.workspace_id or workspace_id
    proj = body.project_id or (default_project_id if body.scope == "project" else None)
    if body.scope == "global":
        ws, proj = None, None
    svc = PromptService(session)
    try:
        row = svc.create_prompt(
            PromptCreate(
                name=body.name,
                key=body.key,
                scope=body.scope,
                description=body.description,
                workspace_id=ws,
                project_id=proj,
                initial_content=body.initial_content,
            )
        )
    except PromptServiceError as exc:
        raise _err(exc) from exc
    return {"prompt": _prompt_row(row)}


@router.get("/{prompt_id}")
def get_prompt(
    prompt_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
) -> dict:
    workspace_id, project_id = ctx
    svc = PromptService(session)
    try:
        row = svc.get_prompt(prompt_id)
        assert_prompt_scope(row, workspace_id=workspace_id, project_id=project_id)
    except PromptServiceError as exc:
        raise _err(exc) from exc
    return {"prompt": _prompt_row(row)}


@router.get("/{prompt_id}/versions")
def list_versions(
    prompt_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
) -> dict:
    workspace_id, project_id = ctx
    svc = PromptService(session)
    try:
        load_prompt_in_context(svc, prompt_id, workspace_id=workspace_id, project_id=project_id)
        versions = svc.list_versions(prompt_id)
    except PromptServiceError as exc:
        raise _err(exc) from exc
    return {"versions": [_version_row(v) for v in versions]}


@router.post("/{prompt_id}/versions")
def create_version(
    prompt_id: uuid.UUID,
    body: PromptVersionCreateRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
) -> dict:
    workspace_id, project_id = ctx
    svc = PromptService(session)
    try:
        load_prompt_in_context(svc, prompt_id, workspace_id=workspace_id, project_id=project_id)
        version = svc.create_version(
            prompt_id=prompt_id,
            content=body.content,
            created_by=body.created_by,
            as_draft=True,
        )
    except PromptServiceError as exc:
        raise _err(exc) from exc
    return {"version": _version_row(version)}


@router.post("/{prompt_id}/versions/{version_id}/publish")
def publish_version(
    prompt_id: uuid.UUID,
    version_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
) -> dict:
    workspace_id, project_id = ctx
    svc = PromptService(session)
    try:
        load_prompt_in_context(svc, prompt_id, workspace_id=workspace_id, project_id=project_id)
        version = svc.publish_version(prompt_id, version_id)
    except PromptServiceError as exc:
        raise _err(exc) from exc
    return {"version": _version_row(version)}


@router.post("/{prompt_id}/versions/{version_id}/rollback")
def rollback_version(
    prompt_id: uuid.UUID,
    version_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
) -> dict:
    workspace_id, project_id = ctx
    svc = PromptService(session)
    try:
        load_prompt_in_context(svc, prompt_id, workspace_id=workspace_id, project_id=project_id)
        version = svc.rollback(prompt_id, version_id)
    except PromptServiceError as exc:
        raise _err(exc) from exc
    return {"version": _version_row(version)}


@router.post("/resolve")
def resolve_prompt(
    body: PromptResolveRequest,
    session: Session = Depends(postgres_session),
    settings: Settings = Depends(require_postgres_settings),
    ctx=Depends(default_project_context),
) -> dict:
    workspace_id, default_project_id = ctx
    project_id = body.project_id or default_project_id
    resolver = PromptResolver(settings, session=session)
    effective = resolver.resolve(body.prompt_key, workspace_id=workspace_id, project_id=project_id)
    from app.prompt_management.sources import FilePromptSource

    svc = PromptService(session)
    layers: list[dict] = []
    for scope, ws, proj in (
        ("project", workspace_id, project_id),
        ("workspace", workspace_id, None),
        ("global", None, None),
    ):
        if scope == "project" and not project_id:
            continue
        if scope == "workspace" and not workspace_id:
            continue
        row = svc._find_prompt_row(body.prompt_key, scope, ws, proj)
        if not row or not row.active_version_id:
            continue
        version = session.get(PromptVersionRow, row.active_version_id)
        if version and version.status == "ACTIVE":
            layers.append(
                {
                    "scope": scope,
                    "prompt_id": str(row.id),
                    "version_number": version.version_number,
                    "status": version.status,
                }
            )

    file_fallback = FilePromptSource().get(body.prompt_key) or ""
    source_label = {
        "project": "Project override",
        "workspace": "Workspace override",
        "global": "Global prompt",
        "file": "File default",
    }.get(effective.source, effective.source)
    return {
        "prompt_key": body.prompt_key,
        "source": effective.source,
        "source_label": source_label,
        "chain": effective.chain or ["project", "workspace", "global", "file"],
        "layers": layers,
        "content": effective.content,
        "file_fallback_preview": file_fallback[:500] if file_fallback else "",
    }
