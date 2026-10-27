from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field

from app.api.v1.deps import default_project_context, postgres_session
from app.connectors.discovery import MetadataDiscoveryService
from app.connectors.errors import ConnectorError
from app.connectors.service import ConnectorRegistryService
from app.core.models import StrictModel

router = APIRouter(prefix="/connectors", tags=["connectors"])


def _err(exc: ConnectorError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


def _registry(session, request: Request) -> ConnectorRegistryService:
    return ConnectorRegistryService(session, settings=request.app.state.settings)


def _discovery(session, request: Request) -> MetadataDiscoveryService:
    return MetadataDiscoveryService(_registry(session, request), settings=request.app.state.settings)


class ConnectorCreateRequest(StrictModel):
    name: str = Field(min_length=1, max_length=256)
    key: str = Field(min_length=1, max_length=128)
    connector_type: str = Field(pattern="^(impala|trino|postgres)$")
    config: dict = Field(default_factory=dict)
    description: str | None = None
    secret_ref: str | None = None
    enabled: bool = True
    metadata: dict | None = None


class ConnectorPatchRequest(StrictModel):
    name: str | None = None
    description: str | None = None
    config: dict | None = None
    secret_ref: str | None = None
    enabled: bool | None = None
    metadata: dict | None = None


class MetadataDescribeRequest(StrictModel):
    catalog: str | None = None
    schema: str | None = None
    table: str = Field(min_length=1, max_length=128)


class MetadataPreviewRequest(StrictModel):
    catalog: str | None = None
    schema: str | None = None
    table: str = Field(min_length=1, max_length=128)
    limit: int = Field(default=10, ge=1, le=100)


@router.get("")
def list_connectors(
    request: Request,
    session=Depends(postgres_session),
    ctx=Depends(default_project_context),
    connector_type: str | None = Query(None),
    enabled: bool | None = Query(None),
):
    ws, proj = ctx
    svc = _registry(session, request)
    rows = svc.list_connectors(
        workspace_id=ws,
        project_id=proj,
        connector_type=connector_type,
        enabled=enabled,
    )
    return {"connectors": [svc.connector_dict(r) for r in rows]}


@router.post("")
def create_connector(
    body: ConnectorCreateRequest,
    request: Request,
    session=Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = ctx
    svc = _registry(session, request)
    try:
        row = svc.create_connector(
            workspace_id=ws,
            project_id=proj,
            name=body.name,
            key=body.key,
            connector_type=body.connector_type,
            config=body.config,
            description=body.description,
            secret_ref=body.secret_ref,
            enabled=body.enabled,
            metadata=body.metadata,
        )
        return {"connector": svc.connector_dict(row)}
    except ConnectorError as exc:
        raise _err(exc) from exc


@router.get("/{connector_id}")
def get_connector(
    connector_id: uuid.UUID,
    request: Request,
    session=Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = ctx
    svc = _registry(session, request)
    try:
        row = svc.get_connector(connector_id, workspace_id=ws, project_id=proj)
        return {"connector": svc.connector_dict(row)}
    except ConnectorError as exc:
        raise _err(exc) from exc


@router.patch("/{connector_id}")
def patch_connector(
    connector_id: uuid.UUID,
    body: ConnectorPatchRequest,
    request: Request,
    session=Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = ctx
    svc = _registry(session, request)
    try:
        row = svc.update_connector(
            connector_id,
            workspace_id=ws,
            project_id=proj,
            patch=body.model_dump(exclude_unset=True),
        )
        return {"connector": svc.connector_dict(row)}
    except ConnectorError as exc:
        raise _err(exc) from exc


@router.get("/{connector_id}/references")
def connector_references(
    connector_id: uuid.UUID,
    request: Request,
    session=Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    from app.semantic_registry.connector_reference import semantic_reference_summary

    ws, proj = ctx
    svc = _registry(session, request)
    try:
        svc.get_connector(connector_id, workspace_id=ws, project_id=proj)
    except ConnectorError as exc:
        raise _err(exc) from exc
    return {"references": semantic_reference_summary(session, connector_id)}


@router.delete("/{connector_id}")
def delete_connector(
    connector_id: uuid.UUID,
    request: Request,
    session=Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = ctx
    svc = _registry(session, request)
    try:
        svc.delete_connector(connector_id, workspace_id=ws, project_id=proj)
        return {"deleted": True}
    except ConnectorError as exc:
        raise _err(exc) from exc


@router.post("/{connector_id}/test")
def test_connector(
    connector_id: uuid.UUID,
    request: Request,
    session=Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = ctx
    svc = _registry(session, request)
    try:
        return svc.test_connector(connector_id, workspace_id=ws, project_id=proj)
    except ConnectorError as exc:
        raise _err(exc) from exc


@router.get("/{connector_id}/capabilities")
def connector_capabilities(
    connector_id: uuid.UUID,
    request: Request,
    session=Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = ctx
    disc = _discovery(session, request)
    try:
        return {"capabilities": disc.capabilities(connector_id, workspace_id=ws, project_id=proj)}
    except ConnectorError as exc:
        raise _err(exc) from exc


@router.get("/{connector_id}/metadata/summary")
def metadata_summary(
    connector_id: uuid.UUID,
    request: Request,
    session=Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = ctx
    disc = _discovery(session, request)
    try:
        return disc.source_summary(connector_id, workspace_id=ws, project_id=proj)
    except ConnectorError as exc:
        raise _err(exc) from exc


@router.get("/{connector_id}/catalogs")
def list_catalogs(
    connector_id: uuid.UUID,
    request: Request,
    session=Depends(postgres_session),
    ctx=Depends(default_project_context),
    refresh: bool = Query(False),
):
    ws, proj = ctx
    disc = _discovery(session, request)
    try:
        return disc.list_catalogs(connector_id, workspace_id=ws, project_id=proj, refresh=refresh)
    except ConnectorError as exc:
        raise _err(exc) from exc


@router.get("/{connector_id}/schemas")
def list_schemas(
    connector_id: uuid.UUID,
    request: Request,
    session=Depends(postgres_session),
    ctx=Depends(default_project_context),
    catalog: str | None = Query(None),
    limit: int | None = Query(None, ge=1, le=500),
    offset: int | None = Query(None, ge=0),
    refresh: bool = Query(False),
):
    ws, proj = ctx
    disc = _discovery(session, request)
    try:
        return disc.list_schemas(
            connector_id,
            workspace_id=ws,
            project_id=proj,
            catalog=catalog,
            limit=limit,
            offset=offset,
            refresh=refresh,
        )
    except ConnectorError as exc:
        raise _err(exc) from exc


@router.get("/{connector_id}/tables")
def list_tables(
    connector_id: uuid.UUID,
    request: Request,
    session=Depends(postgres_session),
    ctx=Depends(default_project_context),
    catalog: str | None = Query(None),
    schema: str | None = Query(None, alias="schema"),
    table_type: str | None = Query(None),
    search: str | None = Query(None),
    limit: int | None = Query(None, ge=1, le=500),
    offset: int | None = Query(None, ge=0),
    refresh: bool = Query(False),
):
    ws, proj = ctx
    disc = _discovery(session, request)
    try:
        return disc.list_tables(
            connector_id,
            workspace_id=ws,
            project_id=proj,
            catalog=catalog,
            schema=schema,
            table_type=table_type,
            search=search,
            limit=limit,
            offset=offset,
            refresh=refresh,
        )
    except ConnectorError as exc:
        raise _err(exc) from exc


@router.post("/{connector_id}/metadata/describe")
def describe_table(
    connector_id: uuid.UUID,
    body: MetadataDescribeRequest,
    request: Request,
    session=Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = ctx
    disc = _discovery(session, request)
    try:
        detail = disc.describe_table(
            connector_id,
            workspace_id=ws,
            project_id=proj,
            catalog=body.catalog,
            schema=body.schema,
            table=body.table,
        )
        return {"table": MetadataDiscoveryService.table_detail_dict(detail)}
    except ConnectorError as exc:
        raise _err(exc) from exc


@router.post("/{connector_id}/metadata/preview")
def preview_table(
    connector_id: uuid.UUID,
    body: MetadataPreviewRequest,
    request: Request,
    session=Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = ctx
    disc = _discovery(session, request)
    try:
        sample = disc.preview_sample(
            connector_id,
            workspace_id=ws,
            project_id=proj,
            catalog=body.catalog,
            schema=body.schema,
            table=body.table,
            limit=body.limit,
        )
        return {"preview": MetadataDiscoveryService.sample_dict(sample)}
    except ConnectorError as exc:
        raise _err(exc) from exc
