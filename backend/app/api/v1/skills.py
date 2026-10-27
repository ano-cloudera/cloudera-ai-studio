from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import default_project_context, postgres_session, require_postgres_settings
from app.api.v1.project_scope import assert_skill_scope, load_skill_in_context
from app.core.config import Settings
from app.services.skill_execution_service import SkillExecutionError, SkillExecutionService
from app.services.skill_service import SkillCreate, SkillService, SkillServiceError, SkillVersionCreate
from app.skills.schemas import (
    SkillCreateRequest,
    SkillExecuteRequest,
    SkillResponse,
    SkillVersionCreateRequest,
    SkillVersionResponse,
)

router = APIRouter(prefix="/skills", tags=["skills"])


def _err(exc: SkillServiceError | SkillExecutionError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


def _skill_row(row) -> dict:
    return SkillResponse(
        id=row.id,
        workspace_id=row.workspace_id,
        project_id=row.project_id,
        name=row.name,
        key=row.key,
        scope=row.scope,
        description=row.description,
        status=row.status,
        active_version_id=row.active_version_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    ).model_dump(mode="json")


def _version_row(row) -> dict:
    return SkillVersionResponse(
        id=row.id,
        skill_id=row.skill_id,
        version_number=row.version_number,
        instructions=row.instructions,
        prompt_key=row.prompt_key,
        input_schema=row.input_schema,
        output_schema=row.output_schema,
        allowed_tools=list(row.allowed_tools or []),
        config=dict(row.config or {}),
        status=row.status,
        created_at=row.created_at,
    ).model_dump(mode="json")


@router.get("")
def list_skills(
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
    scope: str | None = Query(None),
    search: str | None = Query(None),
    project_id: uuid.UUID | None = Query(None),
) -> dict:
    workspace_id, default_project_id = ctx
    svc = SkillService(session)
    rows = svc.list_skills(
        scope=scope,
        workspace_id=workspace_id,
        project_id=project_id or default_project_id if scope == "project" else project_id,
        search=search,
    )
    return {"skills": [_skill_row(r) for r in rows]}


@router.post("")
def create_skill(
    body: SkillCreateRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
) -> dict:
    workspace_id, default_project_id = ctx
    ws = body.workspace_id or workspace_id
    proj = body.project_id or (default_project_id if body.scope == "project" else None)
    svc = SkillService(session)
    try:
        row = svc.create_skill(
            SkillCreate(
                name=body.name,
                key=body.key,
                scope=body.scope,
                description=body.description,
                workspace_id=ws,
                project_id=proj,
                instructions=body.instructions,
                prompt_key=body.prompt_key,
                input_schema=body.input_schema,
                output_schema=body.output_schema,
                allowed_tools=body.allowed_tools,
                config=body.config,
            )
        )
    except SkillServiceError as exc:
        raise _err(exc) from exc
    return {"skill": _skill_row(row)}


@router.get("/{skill_id}")
def get_skill(
    skill_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
) -> dict:
    workspace_id, project_id = ctx
    svc = SkillService(session)
    try:
        row = svc.get_skill(skill_id)
        assert_skill_scope(row, workspace_id=workspace_id, project_id=project_id)
    except SkillServiceError as exc:
        raise _err(exc) from exc
    return {"skill": _skill_row(row)}


@router.get("/{skill_id}/versions")
def list_versions(
    skill_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
) -> dict:
    workspace_id, project_id = ctx
    svc = SkillService(session)
    try:
        load_skill_in_context(svc, skill_id, workspace_id=workspace_id, project_id=project_id)
        versions = svc.list_versions(skill_id)
    except SkillServiceError as exc:
        raise _err(exc) from exc
    return {"versions": [_version_row(v) for v in versions]}


@router.post("/{skill_id}/versions")
def create_version(
    skill_id: uuid.UUID,
    body: SkillVersionCreateRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
) -> dict:
    workspace_id, project_id = ctx
    svc = SkillService(session)
    try:
        load_skill_in_context(svc, skill_id, workspace_id=workspace_id, project_id=project_id)
        version = svc.create_version(
            skill_id=skill_id,
            body=SkillVersionCreate(
                instructions=body.instructions,
                prompt_key=body.prompt_key,
                input_schema=body.input_schema,
                output_schema=body.output_schema,
                allowed_tools=body.allowed_tools,
                config=body.config,
            ),
            as_draft=True,
        )
    except SkillServiceError as exc:
        raise _err(exc) from exc
    return {"version": _version_row(version)}


@router.post("/{skill_id}/versions/{version_id}/publish")
def publish_version(
    skill_id: uuid.UUID,
    version_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
) -> dict:
    workspace_id, project_id = ctx
    svc = SkillService(session)
    try:
        load_skill_in_context(svc, skill_id, workspace_id=workspace_id, project_id=project_id)
        version = svc.publish_version(skill_id, version_id)
    except SkillServiceError as exc:
        raise _err(exc) from exc
    return {"version": _version_row(version)}


@router.post("/{skill_id}/versions/{version_id}/rollback")
def rollback_version(
    skill_id: uuid.UUID,
    version_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
) -> dict:
    workspace_id, project_id = ctx
    svc = SkillService(session)
    try:
        load_skill_in_context(svc, skill_id, workspace_id=workspace_id, project_id=project_id)
        version = svc.rollback(skill_id, version_id)
    except SkillServiceError as exc:
        raise _err(exc) from exc
    return {"version": _version_row(version)}


@router.post("/{skill_id}/execute")
async def execute_skill(
    skill_id: uuid.UUID,
    body: SkillExecuteRequest,
    request: Request,
    session: Session = Depends(postgres_session),
    settings: Settings = Depends(require_postgres_settings),
    ctx=Depends(default_project_context),
) -> dict:
    workspace_id, project_id = ctx
    chat_service = request.app.state.chat_service
    executor = SkillExecutionService(settings, session, chat_service=chat_service)
    try:
        return await executor.execute(
            skill_id,
            user_input=body.input,
            conversation_id=body.conversation_id,
            workspace_id=workspace_id,
            project_id=project_id,
            runtime_context=body.context,
        )
    except (SkillExecutionError, SkillServiceError) as exc:
        raise _err(exc) from exc
