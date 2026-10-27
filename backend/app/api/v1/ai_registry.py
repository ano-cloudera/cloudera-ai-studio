from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field

from app.ai_registry.errors import AiRegistryError
from app.ai_registry.services import (
    ModelAssignmentService,
    ModelRegistryService,
    ProviderRegistryService,
    ProviderTestService,
)
from app.ai_registry.types import CAPABILITIES, MODEL_TYPES, PROVIDER_TYPES
from app.api.v1.deps import default_project_context, postgres_session
from app.core.models import StrictModel

router = APIRouter(prefix="/ai", tags=["ai-model-registry"])


def _err(exc: AiRegistryError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


class ProviderCreateRequest(StrictModel):
    name: str = Field(min_length=1, max_length=256)
    key: str = Field(min_length=1, max_length=128)
    provider_type: str
    base_url: str | None = None
    secret_ref: str | None = None
    enabled: bool = True
    config_json: dict | None = None


class ProviderPatchRequest(StrictModel):
    name: str | None = None
    base_url: str | None = None
    secret_ref: str | None = None
    enabled: bool | None = None
    config_json: dict | None = None


class ModelCreateRequest(StrictModel):
    provider_id: uuid.UUID
    name: str = Field(min_length=1, max_length=256)
    key: str = Field(min_length=1, max_length=128)
    model_id: str = Field(min_length=1, max_length=256)
    model_type: str
    enabled: bool = True
    context_window: int | None = Field(default=None, gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    supports_streaming: bool | None = None
    supports_tools: bool | None = None
    supports_json_mode: bool | None = None
    supports_vision: bool | None = None
    config_json: dict | None = None


class ModelPatchRequest(StrictModel):
    name: str | None = None
    model_id: str | None = None
    model_type: str | None = None
    enabled: bool | None = None
    context_window: int | None = Field(default=None, gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    supports_streaming: bool | None = None
    supports_tools: bool | None = None
    supports_json_mode: bool | None = None
    supports_vision: bool | None = None
    config_json: dict | None = None


class AssignmentPutRequest(StrictModel):
    model_id: uuid.UUID
    enabled: bool = True


@router.get("/providers")
def list_providers(
    session=Depends(postgres_session),
    ctx=Depends(default_project_context),
    provider_type: str | None = Query(None),
    enabled: bool | None = Query(None),
):
    ws, proj = ctx
    svc = ProviderRegistryService(session)
    rows = svc.list_providers(workspace_id=ws, project_id=proj, provider_type=provider_type, enabled=enabled)
    return {"providers": [svc.provider_dict(r) for r in rows]}


@router.post("/providers")
def create_provider(body: ProviderCreateRequest, session=Depends(postgres_session), ctx=Depends(default_project_context)):
    ws, proj = ctx
    if body.provider_type.upper() not in PROVIDER_TYPES:
        raise _err(AiRegistryError("PROVIDER_UNREACHABLE", "Invalid provider_type", 422))
    svc = ProviderRegistryService(session)
    try:
        row = svc.create_provider(
            workspace_id=ws,
            project_id=proj,
            name=body.name,
            key=body.key,
            provider_type=body.provider_type,
            base_url=body.base_url,
            secret_ref=body.secret_ref,
            enabled=body.enabled,
            config_json=body.config_json,
        )
        return {"provider": svc.provider_dict(row)}
    except AiRegistryError as exc:
        raise _err(exc) from exc


@router.get("/providers/{provider_id}")
def get_provider(provider_id: uuid.UUID, session=Depends(postgres_session), ctx=Depends(default_project_context)):
    ws, proj = ctx
    svc = ProviderRegistryService(session)
    try:
        row = svc.get_provider(provider_id, workspace_id=ws, project_id=proj)
        return {"provider": svc.provider_dict(row)}
    except AiRegistryError as exc:
        raise _err(exc) from exc


@router.patch("/providers/{provider_id}")
def patch_provider(
    provider_id: uuid.UUID,
    body: ProviderPatchRequest,
    session=Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = ctx
    svc = ProviderRegistryService(session)
    try:
        row = svc.update_provider(
            provider_id,
            workspace_id=ws,
            project_id=proj,
            patch=body.model_dump(exclude_unset=True),
        )
        return {"provider": svc.provider_dict(row)}
    except AiRegistryError as exc:
        raise _err(exc) from exc


@router.delete("/providers/{provider_id}")
def delete_provider(provider_id: uuid.UUID, session=Depends(postgres_session), ctx=Depends(default_project_context)):
    ws, proj = ctx
    svc = ProviderRegistryService(session)
    try:
        svc.delete_provider(provider_id, workspace_id=ws, project_id=proj)
        return {"deleted": True}
    except AiRegistryError as exc:
        raise _err(exc) from exc


@router.post("/providers/{provider_id}/test")
def test_provider(provider_id: uuid.UUID, session=Depends(postgres_session), ctx=Depends(default_project_context)):
    ws, proj = ctx
    svc = ProviderTestService(session)
    try:
        return svc.test_provider(provider_id, workspace_id=ws, project_id=proj)
    except AiRegistryError as exc:
        raise _err(exc) from exc


@router.get("/providers/{provider_id}/remote-models")
def list_provider_remote_models(
    provider_id: uuid.UUID,
    session=Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = ctx
    svc = ProviderTestService(session)
    try:
        return svc.list_provider_remote_models(provider_id, workspace_id=ws, project_id=proj)
    except AiRegistryError as exc:
        raise _err(exc) from exc


@router.get("/models")
def list_models(
    session=Depends(postgres_session),
    ctx=Depends(default_project_context),
    provider_id: uuid.UUID | None = Query(None),
    model_type: str | None = Query(None),
    enabled: bool | None = Query(None),
):
    ws, proj = ctx
    svc = ModelRegistryService(session)
    rows = svc.list_models(
        workspace_id=ws,
        project_id=proj,
        provider_id=provider_id,
        model_type=model_type,
        enabled=enabled,
    )
    return {"models": [svc.model_dict(r) for r in rows]}


@router.post("/models")
def create_model(body: ModelCreateRequest, session=Depends(postgres_session), ctx=Depends(default_project_context)):
    ws, proj = ctx
    if body.model_type.upper() not in MODEL_TYPES:
        raise _err(AiRegistryError("MODEL_INVALID", "Invalid model_type", 422))
    svc = ModelRegistryService(session)
    try:
        row = svc.create_model(
            workspace_id=ws,
            project_id=proj,
            provider_id=body.provider_id,
            name=body.name,
            key=body.key,
            model_id=body.model_id,
            model_type=body.model_type,
            enabled=body.enabled,
            context_window=body.context_window,
            max_output_tokens=body.max_output_tokens,
            supports_streaming=body.supports_streaming,
            supports_tools=body.supports_tools,
            supports_json_mode=body.supports_json_mode,
            supports_vision=body.supports_vision,
            config_json=body.config_json,
        )
        return {"model": svc.model_dict(row)}
    except AiRegistryError as exc:
        raise _err(exc) from exc


@router.get("/models/{model_id}")
def get_model(model_id: uuid.UUID, session=Depends(postgres_session), ctx=Depends(default_project_context)):
    ws, proj = ctx
    svc = ModelRegistryService(session)
    try:
        row = svc.get_model(model_id, workspace_id=ws, project_id=proj)
        return {"model": svc.model_dict(row)}
    except AiRegistryError as exc:
        raise _err(exc) from exc


@router.patch("/models/{model_id}")
def patch_model(
    model_id: uuid.UUID,
    body: ModelPatchRequest,
    session=Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = ctx
    svc = ModelRegistryService(session)
    try:
        row = svc.update_model(
            model_id,
            workspace_id=ws,
            project_id=proj,
            patch=body.model_dump(exclude_unset=True),
        )
        return {"model": svc.model_dict(row)}
    except AiRegistryError as exc:
        raise _err(exc) from exc


@router.delete("/models/{model_id}")
def delete_model(model_id: uuid.UUID, session=Depends(postgres_session), ctx=Depends(default_project_context)):
    ws, proj = ctx
    svc = ModelRegistryService(session)
    try:
        svc.delete_model(model_id, workspace_id=ws, project_id=proj)
        return {"deleted": True}
    except AiRegistryError as exc:
        raise _err(exc) from exc


@router.post("/models/{model_id}/test")
def test_model(model_id: uuid.UUID, session=Depends(postgres_session), ctx=Depends(default_project_context)):
    ws, proj = ctx
    svc = ProviderTestService(session)
    try:
        return svc.test_model(model_id, workspace_id=ws, project_id=proj)
    except AiRegistryError as exc:
        raise _err(exc) from exc


@router.get("/assignments")
def list_assignments(session=Depends(postgres_session), ctx=Depends(default_project_context)):
    ws, proj = ctx
    svc = ModelAssignmentService(session)
    return {"assignments": svc.list_assignments(workspace_id=ws, project_id=proj)}


@router.delete("/assignments/{capability}")
def delete_assignment(
    capability: str,
    session=Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    cap = capability.upper()
    if cap not in CAPABILITIES:
        raise _err(AiRegistryError("INVALID_ASSIGNMENT", f"Unknown capability: {capability}", 422))
    ws, proj = ctx
    svc = ModelAssignmentService(session)
    assignment = svc.delete_project_assignment(capability=cap, workspace_id=ws, project_id=proj)
    return {"assignment": assignment}


@router.put("/assignments/{capability}")
def put_assignment(
    capability: str,
    body: AssignmentPutRequest,
    session=Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    cap = capability.upper()
    if cap not in CAPABILITIES:
        raise _err(AiRegistryError("INVALID_ASSIGNMENT", f"Unknown capability: {capability}", 422))
    ws, proj = ctx
    svc = ModelAssignmentService(session)
    try:
        assignment = svc.put_assignment(
            capability=cap,
            model_id=body.model_id,
            workspace_id=ws,
            project_id=proj,
            enabled=body.enabled,
        )
        return {"assignment": assignment}
    except AiRegistryError as exc:
        raise _err(exc) from exc
