from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field
from sqlalchemy.orm import Session

from app.api.v1.deps import default_project_context, postgres_session
from app.core.config import get_settings
from app.core.models import StrictModel
from app.documents.bulk_schemas import BulkDeleteResponse
from app.semantic_registry.metric_validation import validate_metric_draft
from app.semantic_runtime.loader import SemanticRuntimeLoader
from app.semantic_runtime.service import SemanticRuntimeError, SemanticRuntimeService
from app.semantic_registry.list_query import apply_list_query
from app.services.semantic_overview_service import SemanticOverviewService
from app.services.semantic_publish_orchestration import SemanticPublishOrchestrationService
from app.services.semantic_bulk_delete_service import SemanticBulkDeleteService
from app.services.semantic_registry_service import SemanticModelCreate, SemanticRegistryError, SemanticRegistryService
from app.services.semantic_suggestion_accept_service import SemanticSuggestionAcceptService
from app.services.semantic_suggestions_service import SemanticSuggestionsService

_ENTITY_SORT = frozenset({"name", "key", "updated_at", "created_at", "modified"})
_METRIC_SORT = frozenset({"name", "key", "updated_at", "created_at", "modified"})
_DIMENSION_SORT = frozenset({"name", "key", "updated_at", "created_at", "modified"})
_RELATIONSHIP_SORT = frozenset({"name", "key", "updated_at", "created_at", "modified"})
_TERM_SORT = frozenset({"name", "key", "term", "updated_at", "created_at", "modified"})
_RECENT_SORT = frozenset({"name", "type", "modified", "updated_at", "created_at"})

router = APIRouter(prefix="/semantic", tags=["semantic"])


def _err(exc: SemanticRegistryError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


def _runtime_err(exc: SemanticRuntimeError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


def _ctx_ids(ctx) -> tuple[uuid.UUID, uuid.UUID]:
    return ctx[0], ctx[1]


class SemanticModelCreateRequest(StrictModel):
    name: str = Field(min_length=1, max_length=256)
    key: str = Field(min_length=1, max_length=128)
    description: str | None = None


class SemanticModelPatchRequest(StrictModel):
    name: str | None = None
    description: str | None = None


class EntityCreateRequest(StrictModel):
    key: str
    name: str
    description: str | None = None
    source_type: str = "logical"
    catalog: str | None = None
    db_schema: str | None = None
    table_name: str | None = None
    view_name: str | None = None
    primary_key: str | None = None
    connection_id: str | None = None
    metadata: dict | None = None


class MetricCreateRequest(StrictModel):
    key: str
    name: str
    expression: str
    source_entity_key: str
    description: str | None = None
    business_definition: str | None = None
    aggregation: str | None = None
    format: str | None = None
    unit: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    metadata: dict | None = None


class DimensionCreateRequest(StrictModel):
    key: str
    name: str
    source_entity_key: str
    source_column: str
    description: str | None = None
    data_type: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    metadata: dict | None = None


class RelationshipCreateRequest(StrictModel):
    key: str
    name: str
    from_entity_key: str
    to_entity_key: str
    join_expression: str
    relationship_type: str = "many_to_one"
    join_type: str = "inner"
    description: str | None = None
    metadata: dict | None = None


class TermCreateRequest(StrictModel):
    key: str
    term: str
    definition: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    related_metric_keys: list[str] = Field(default_factory=list)
    related_dimension_keys: list[str] = Field(default_factory=list)
    related_entity_keys: list[str] = Field(default_factory=list)
    metadata: dict | None = None


class EntityUpdateRequest(StrictModel):
    name: str | None = None
    description: str | None = None
    source_type: str | None = None
    catalog: str | None = None
    db_schema: str | None = None
    table_name: str | None = None
    view_name: str | None = None
    primary_key: str | None = None
    connection_id: str | None = None
    metadata: dict | None = None


class MetricUpdateRequest(StrictModel):
    name: str | None = None
    description: str | None = None
    business_definition: str | None = None
    expression: str | None = None
    aggregation: str | None = None
    source_entity_key: str | None = None
    format: str | None = None
    unit: str | None = None
    synonyms: list[str] | None = None
    metadata: dict | None = None


class DimensionUpdateRequest(StrictModel):
    name: str | None = None
    description: str | None = None
    source_entity_key: str | None = None
    source_column: str | None = None
    data_type: str | None = None
    synonyms: list[str] | None = None
    metadata: dict | None = None


class RelationshipUpdateRequest(StrictModel):
    name: str | None = None
    from_entity_key: str | None = None
    to_entity_key: str | None = None
    relationship_type: str | None = None
    join_type: str | None = None
    join_expression: str | None = None
    description: str | None = None
    metadata: dict | None = None


class TermUpdateRequest(StrictModel):
    term: str | None = None
    definition: str | None = None
    synonyms: list[str] | None = None
    related_metric_keys: list[str] | None = None
    related_dimension_keys: list[str] | None = None
    related_entity_keys: list[str] | None = None
    metadata: dict | None = None


class SemanticBulkDeleteRequest(StrictModel):
    ids: list[str] = Field(min_length=1)


class MetricValidateRequest(StrictModel):
    metric_id: str | None = None
    name: str
    business_definition: str | None = None
    expression: str
    aggregation: str | None = None
    source_entity_key: str


class OssieImportRequest(StrictModel):
    model_key: str = Field(min_length=1, max_length=128)
    model_name: str | None = None
    dry_run: bool = False


class ValidateVersionRequest(StrictModel):
    mode: str = Field(default="full", pattern="^(structural|source|full)$")
    source_mode: str | None = Field(default=None, pattern="^(metadata_only|safe_query)$")


class PublishToAskDataRequest(StrictModel):
    version_id: str | None = None


class SemanticSuggestionsRequest(StrictModel):
    connection_id: str
    tables: list[str] = Field(default_factory=list, max_length=50)


class SuggestionSelectionRequest(StrictModel):
    suggestion_id: str
    type: str
    accepted: bool = False
    payload: dict = Field(default_factory=dict)
    changes: dict = Field(default_factory=dict)


class BootstrapTableRequest(StrictModel):
    connection_id: str
    key: str
    name: str | None = None
    description: str | None = None
    catalog: str | None = None
    schema: str | None = None
    table_name: str | None = None
    primary_key: str | None = None


class AcceptSuggestionsRequest(StrictModel):
    version_id: str | None = None
    bootstrap_tables: list[BootstrapTableRequest] = Field(default_factory=list)
    selections: list[SuggestionSelectionRequest] = Field(default_factory=list)


def _entity_dict(r) -> dict:
    return {
        "id": str(r.id),
        "key": r.key,
        "name": r.name,
        "description": r.description,
        "source_type": r.source_type,
        "catalog": r.catalog,
        "schema": r.schema,
        "table_name": r.table_name,
        "view_name": r.view_name,
        "primary_key": r.primary_key,
        "connection_id": str(r.connection_id) if r.connection_id else None,
        "metadata": r.metadata_ or {},
    }


def _metric_dict(r) -> dict:
    return {
        "id": str(r.id),
        "key": r.key,
        "name": r.name,
        "description": r.description,
        "business_definition": r.business_definition,
        "expression": r.expression,
        "aggregation": r.aggregation,
        "source_entity_key": r.source_entity_key,
        "format": r.format,
        "unit": r.unit,
        "synonyms": list(r.synonyms or []),
        "metadata": r.metadata_ or {},
    }


def _dimension_dict(r) -> dict:
    return {
        "id": str(r.id),
        "key": r.key,
        "name": r.name,
        "description": r.description,
        "source_entity_key": r.source_entity_key,
        "source_column": r.source_column,
        "data_type": r.data_type,
        "synonyms": list(r.synonyms or []),
        "metadata": r.metadata_ or {},
    }


def _relationship_dict(r) -> dict:
    return {
        "id": str(r.id),
        "key": r.key,
        "name": r.name,
        "from_entity_key": r.from_entity_key,
        "to_entity_key": r.to_entity_key,
        "relationship_type": r.relationship_type,
        "join_type": r.join_type,
        "join_expression": r.join_expression,
        "description": r.description,
        "metadata": r.metadata_ or {},
    }


def _term_dict(r) -> dict:
    return {
        "id": str(r.id),
        "key": r.key,
        "term": r.term,
        "definition": r.definition,
        "synonyms": list(r.synonyms or []),
        "related_metric_keys": list(r.related_metric_keys or []),
        "related_dimension_keys": list(r.related_dimension_keys or []),
        "related_entity_keys": list(r.related_entity_keys or []),
        "metadata": r.metadata_ or {},
    }


def _model_dict(row) -> dict:
    return {
        "id": str(row.id),
        "workspace_id": str(row.workspace_id),
        "project_id": str(row.project_id),
        "name": row.name,
        "key": row.key,
        "description": row.description,
        "active_version_id": str(row.active_version_id) if row.active_version_id else None,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _version_dict(row) -> dict:
    return {
        "id": str(row.id),
        "semantic_model_id": str(row.semantic_model_id),
        "version_number": row.version_number,
        "status": row.status,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "published_at": row.published_at,
        "runtime_adapter": row.runtime_adapter,
        "runtime_artifact_uri": row.runtime_artifact_uri,
        "runtime_artifact_checksum": row.runtime_artifact_checksum,
        "runtime_artifact_version": row.runtime_artifact_version,
        "last_validation_run_id": str(row.last_validation_run_id) if row.last_validation_run_id else None,
        "activation_readiness": row.activation_readiness,
        "validated_at": row.validated_at,
    }


@router.get("/models")
def list_models(session: Session = Depends(postgres_session), ctx=Depends(default_project_context), search: str | None = Query(None)):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    return {"models": [_model_dict(r) for r in svc.list_models(workspace_id=ws, project_id=proj, search=search)]}


@router.post("/models")
def create_model(body: SemanticModelCreateRequest, session: Session = Depends(postgres_session), ctx=Depends(default_project_context)):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        row = svc.create_model(SemanticModelCreate(name=body.name, key=body.key, workspace_id=ws, project_id=proj, description=body.description))
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {"model": _model_dict(row)}


@router.get("/models/{model_id}/overview")
def get_model_overview(model_id: uuid.UUID, session: Session = Depends(postgres_session), ctx=Depends(default_project_context)):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticOverviewService(session)
    try:
        payload = svc.model_overview(model_id=model_id, workspace_id=ws, project_id=proj)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Model not found"}) from None
    return payload


@router.get("/models/{model_id}")
def get_model(model_id: uuid.UUID, session: Session = Depends(postgres_session), ctx=Depends(default_project_context)):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        row = svc.get_model(model_id, workspace_id=ws, project_id=proj)
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {"model": _model_dict(row)}


@router.patch("/models/{model_id}")
def patch_model(
    model_id: uuid.UUID,
    body: SemanticModelPatchRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        row = svc.patch_model(model_id, workspace_id=ws, project_id=proj, name=body.name, description=body.description)
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {"model": _model_dict(row)}


@router.post("/models/{model_id}/publish-to-ask-data")
def publish_to_ask_data(
    model_id: uuid.UUID,
    body: PublishToAskDataRequest | None = None,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    version_uuid = None
    if body and body.version_id:
        try:
            version_uuid = uuid.UUID(body.version_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "invalid_version_id", "message": str(exc)}) from exc
    svc = SemanticPublishOrchestrationService(session)
    try:
        result = svc.publish_to_ask_data(
            model_id,
            workspace_id=ws,
            project_id=proj,
            version_id=version_uuid,
        )
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    if result.get("status") == "needs_attention":
        raise HTTPException(status_code=422, detail=result)
    if result.get("status") == "activation_failed":
        raise HTTPException(status_code=502, detail=result)
    return result


@router.post("/suggestions")
def semantic_suggestions(
    body: SemanticSuggestionsRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    try:
        connection_id = uuid.UUID(body.connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "invalid_connection_id", "message": str(exc)}) from exc
    svc = SemanticSuggestionsService(session)
    try:
        result = svc.suggest(
            workspace_id=ws,
            project_id=proj,
            connection_id=connection_id,
            tables=body.tables,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"code": "suggestion_failed", "message": str(exc)}) from exc
    return result.to_dict()


@router.post("/models/{model_id}/suggestions/accept")
def accept_semantic_suggestions(
    model_id: uuid.UUID,
    body: AcceptSuggestionsRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    version_uuid = None
    if body.version_id:
        try:
            version_uuid = uuid.UUID(body.version_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "invalid_version_id", "message": str(exc)}) from exc
    svc = SemanticSuggestionAcceptService(session)
    try:
        result = svc.accept(
            model_id,
            workspace_id=ws,
            project_id=proj,
            version_id=version_uuid,
            bootstrap_tables=[t.model_dump() for t in body.bootstrap_tables],
            selections=[s.model_dump() for s in body.selections],
        )
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    session.commit()
    return result.to_dict()


@router.get("/models/{model_id}/versions")
def list_versions(model_id: uuid.UUID, session: Session = Depends(postgres_session), ctx=Depends(default_project_context)):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        versions = svc.list_versions(model_id, workspace_id=ws, project_id=proj)
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {"versions": [_version_dict(v) for v in versions]}


@router.post("/models/{model_id}/versions")
def create_version(model_id: uuid.UUID, session: Session = Depends(postgres_session), ctx=Depends(default_project_context)):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        version = svc.create_version(model_id, workspace_id=ws, project_id=proj)
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {"version": _version_dict(version)}


@router.get("/versions/{version_id}")
def get_version(version_id: uuid.UUID, session: Session = Depends(postgres_session), ctx=Depends(default_project_context)):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        version = svc.get_version(version_id, workspace_id=ws, project_id=proj)
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {"version": _version_dict(version)}


@router.post("/versions/{version_id}/clone")
def clone_version(version_id: uuid.UUID, session: Session = Depends(postgres_session), ctx=Depends(default_project_context)):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        version = svc.clone_version(version_id, workspace_id=ws, project_id=proj)
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {"version": _version_dict(version)}


@router.post("/versions/{version_id}/validate")
def validate_version(
    version_id: uuid.UUID,
    body: ValidateVersionRequest | None = None,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    req = body or ValidateVersionRequest()
    try:
        return svc.validate_version(
            version_id,
            workspace_id=ws,
            project_id=proj,
            mode=req.mode,
            source_mode=req.source_mode,
        )
    except SemanticRegistryError as exc:
        raise _err(exc) from exc


@router.get("/versions/{version_id}/readiness")
def get_readiness(version_id: uuid.UUID, session: Session = Depends(postgres_session), ctx=Depends(default_project_context)):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        return svc.get_readiness(version_id, workspace_id=ws, project_id=proj)
    except SemanticRegistryError as exc:
        raise _err(exc) from exc


@router.get("/versions/{version_id}/validation-runs")
def list_validation_runs(
    version_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
    limit: int = Query(20, ge=1, le=100),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        runs = svc.list_validation_runs(version_id, workspace_id=ws, project_id=proj, limit=limit)
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {
        "runs": [
            {
                "id": str(r.id),
                "semantic_version_id": str(r.semantic_version_id),
                "started_at": r.started_at,
                "completed_at": r.completed_at,
                "status": r.status,
                "mode": r.mode,
                "summary": r.summary,
                "validator_version": r.validator_version,
            }
            for r in runs
        ]
    }


@router.get("/validation-runs/{run_id}")
def get_validation_run(run_id: uuid.UUID, session: Session = Depends(postgres_session), ctx=Depends(default_project_context)):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        return svc.get_validation_run(run_id, workspace_id=ws, project_id=proj)
    except SemanticRegistryError as exc:
        raise _err(exc) from exc


@router.get("/versions/{version_id}/diff")
def diff_version(
    version_id: uuid.UUID,
    against: uuid.UUID = Query(..., alias="against"),
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        return svc.diff_version(version_id, against_version_id=against, workspace_id=ws, project_id=proj)
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)}) from exc


@router.get("/validators/health")
def validator_health(session: Session = Depends(postgres_session), ctx=Depends(default_project_context)):
    _ctx_ids(ctx)
    return SemanticRegistryService(session).source_validator_health()


@router.post("/versions/{version_id}/publish")
def publish_version(version_id: uuid.UUID, session: Session = Depends(postgres_session), ctx=Depends(default_project_context)):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        version = svc.publish_version(version_id, workspace_id=ws, project_id=proj)
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {"version": _version_dict(version)}


@router.post("/versions/{version_id}/rollback")
def rollback_version(version_id: uuid.UUID, session: Session = Depends(postgres_session), ctx=Depends(default_project_context)):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        version = svc.rollback_version(version_id, workspace_id=ws, project_id=proj)
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {"version": _version_dict(version)}


@router.post("/versions/{version_id}/artifact-preview")
def artifact_preview(version_id: uuid.UUID, session: Session = Depends(postgres_session), ctx=Depends(default_project_context)):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        return svc.artifact_preview(version_id, workspace_id=ws, project_id=proj, write_file=False)
    except SemanticRegistryError as exc:
        raise _err(exc) from exc


@router.get("/resolve")
def resolve_active(
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
    semantic_model_key: str = Query(...),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    resolved = svc.resolve_active(workspace_id=ws, project_id=proj, semantic_model_key=semantic_model_key)
    if not resolved:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "No active semantic version"})
    return {"model": _model_dict(resolved.model), "version": _version_dict(resolved.version)}


@router.get("/versions/{version_id}/entities")
def list_entities(
    version_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
    search: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    order: str | None = Query(default=None),
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=200),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        version = svc.get_version(version_id, workspace_id=ws, project_id=proj)
        rows = svc.list_entities(version_id, workspace_id=ws, project_id=proj)
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    modified = version.updated_at.isoformat() if version.updated_at else None
    for row in rows:
        row.updated_at = version.updated_at  # type: ignore[attr-defined]
    filtered, total = apply_list_query(
        rows,
        search=search,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
        allowed_sort=_ENTITY_SORT,
        search_text=lambda r: " ".join(
            p for p in (r.name, r.key, r.description, r.schema, r.table_name, r.view_name) if p
        ),
    )
    entities = [{**_entity_dict(r), "modified_at": modified} for r in filtered]
    if page is None and page_size is None and not search and not sort and not order:
        return {"entities": entities}
    return {
        "entities": entities,
        "total": total,
        "page": page or 1,
        "page_size": page_size or total,
    }


@router.post("/versions/{version_id}/entities")
def create_entity(
    version_id: uuid.UUID,
    body: EntityCreateRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        row = svc.create_entity(version_id, workspace_id=ws, project_id=proj, data=body.model_dump())
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {"entity": _entity_dict(row)}


@router.patch("/versions/{version_id}/entities/{entity_id}")
def patch_entity(
    version_id: uuid.UUID,
    entity_id: uuid.UUID,
    body: EntityUpdateRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        row = svc.update_entity(
            version_id,
            entity_id,
            workspace_id=ws,
            project_id=proj,
            data=body.model_dump(exclude_unset=True),
        )
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {"entity": _entity_dict(row)}


@router.delete("/versions/{version_id}/entities/{entity_id}")
def delete_entity(
    version_id: uuid.UUID,
    entity_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        svc.delete_entity(version_id, entity_id, workspace_id=ws, project_id=proj)
        session.commit()
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {"deleted": True}


@router.post("/versions/{version_id}/entities/bulk-delete", response_model=BulkDeleteResponse)
def bulk_delete_entities(
    version_id: uuid.UUID,
    body: SemanticBulkDeleteRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticBulkDeleteService(session, get_settings())
    try:
        return svc.delete_entities(version_id, body.ids, workspace_id=ws, project_id=proj)
    except SemanticRegistryError as exc:
        raise _err(exc) from exc


class EntityImportPreviewRequest(StrictModel):
    connector_id: str
    catalog: str | None = None
    schema: str | None = None
    table: str = Field(min_length=1, max_length=256)


class EntityImportRequest(StrictModel):
    connector_id: str
    catalog: str | None = None
    schema: str | None = None
    table: str = Field(min_length=1, max_length=256)
    name: str = Field(min_length=1, max_length=256)
    key: str = Field(min_length=1, max_length=128)
    description: str | None = None
    dimension_columns: list[str] = Field(default_factory=list)


@router.post("/versions/{version_id}/entities/import-preview")
def import_entity_preview(
    version_id: uuid.UUID,
    body: EntityImportPreviewRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    from app.semantic_registry.entity_import import SemanticEntityImportService

    ws, proj = _ctx_ids(ctx)
    svc = SemanticEntityImportService(session)
    try:
        preview = svc.import_preview(
            version_id,
            workspace_id=ws,
            project_id=proj,
            connector_id=uuid.UUID(body.connector_id),
            catalog=body.catalog,
            schema=body.schema,
            table=body.table,
        )
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {"preview": preview}


@router.post("/versions/{version_id}/entities/import")
def import_entity(
    version_id: uuid.UUID,
    body: EntityImportRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    from app.semantic_registry.entity_import import SemanticEntityImportService

    ws, proj = _ctx_ids(ctx)
    svc = SemanticEntityImportService(session)
    try:
        result = svc.import_entity(
            version_id,
            workspace_id=ws,
            project_id=proj,
            connector_id=uuid.UUID(body.connector_id),
            catalog=body.catalog,
            schema=body.schema,
            table=body.table,
            name=body.name,
            key=body.key,
            description=body.description,
            dimension_columns=body.dimension_columns,
        )
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {
        "entity": _entity_dict(result.entity),
        "import": {
            "dimensions_created": result.dimensions_created,
            "columns_discovered": result.columns_discovered,
            "warnings": result.warnings,
        },
    }


@router.get("/versions/{version_id}/metrics")
def list_metrics(
    version_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
    search: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    order: str | None = Query(default=None),
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=200),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        version = svc.get_version(version_id, workspace_id=ws, project_id=proj)
        rows = svc.list_metrics(version_id, workspace_id=ws, project_id=proj)
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    modified = version.updated_at.isoformat() if version.updated_at else None
    for row in rows:
        row.updated_at = version.updated_at  # type: ignore[attr-defined]
    filtered, total = apply_list_query(
        rows,
        search=search,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
        allowed_sort=_METRIC_SORT,
        search_text=lambda r: " ".join(
            p for p in (r.name, r.key, r.business_definition, r.expression, *(r.synonyms or [])) if p
        ),
    )
    metrics = [{**_metric_dict(r), "modified_at": modified} for r in filtered]
    if page is None and page_size is None and not search and not sort and not order:
        return {"metrics": metrics}
    return {"metrics": metrics, "total": total, "page": page or 1, "page_size": page_size or total}


@router.post("/versions/{version_id}/metrics")
def create_metric(
    version_id: uuid.UUID,
    body: MetricCreateRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        row = svc.create_metric(version_id, workspace_id=ws, project_id=proj, data=body.model_dump())
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {"metric": _metric_dict(row)}


@router.patch("/versions/{version_id}/metrics/{metric_id}")
def patch_metric(
    version_id: uuid.UUID,
    metric_id: uuid.UUID,
    body: MetricUpdateRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        row = svc.update_metric(
            version_id,
            metric_id,
            workspace_id=ws,
            project_id=proj,
            data=body.model_dump(exclude_unset=True),
        )
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {"metric": _metric_dict(row)}


@router.delete("/versions/{version_id}/metrics/{metric_id}")
def delete_metric(
    version_id: uuid.UUID,
    metric_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        svc.delete_metric(version_id, metric_id, workspace_id=ws, project_id=proj)
        session.commit()
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {"deleted": True}


@router.post("/versions/{version_id}/metrics/bulk-delete", response_model=BulkDeleteResponse)
def bulk_delete_metrics(
    version_id: uuid.UUID,
    body: SemanticBulkDeleteRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticBulkDeleteService(session, get_settings())
    try:
        return svc.delete_metrics(version_id, body.ids, workspace_id=ws, project_id=proj)
    except SemanticRegistryError as exc:
        raise _err(exc) from exc


@router.post("/versions/{version_id}/metrics/validate")
def validate_metric(
    version_id: uuid.UUID,
    body: MetricValidateRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        svc.get_version(version_id, workspace_id=ws, project_id=proj)
        entities = svc.list_entities(version_id, workspace_id=ws, project_id=proj)
        dimensions = svc.list_dimensions(version_id, workspace_id=ws, project_id=proj)
        metrics = svc.list_metrics(version_id, workspace_id=ws, project_id=proj)
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    entity_keys = {e.key for e in entities}
    existing_names = {
        m.name.strip().casefold()
        for m in metrics
        if not body.metric_id or str(m.id) != str(body.metric_id)
    }
    result = validate_metric_draft(
        name=body.name,
        business_definition=body.business_definition,
        expression=body.expression,
        aggregation=body.aggregation,
        source_entity_key=body.source_entity_key,
        entity_keys=entity_keys,
        dimensions=dimensions,
        existing_metric_names=existing_names,
        metric_id=body.metric_id,
    )
    return {
        "valid": result.valid,
        "issues": [{"field": i.field, "message": i.message} for i in result.issues],
        "form_message": result.form_message,
    }


@router.get("/versions/{version_id}/dimensions")
def list_dimensions(
    version_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
    search: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    order: str | None = Query(default=None),
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=200),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        version = svc.get_version(version_id, workspace_id=ws, project_id=proj)
        rows = svc.list_dimensions(version_id, workspace_id=ws, project_id=proj)
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    modified = version.updated_at.isoformat() if version.updated_at else None
    for row in rows:
        row.updated_at = version.updated_at  # type: ignore[attr-defined]
    filtered, total = apply_list_query(
        rows,
        search=search,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
        allowed_sort=_DIMENSION_SORT,
        search_text=lambda r: " ".join(
            p for p in (r.name, r.key, r.description, r.source_column, r.source_entity_key, *(r.synonyms or [])) if p
        ),
    )
    dimensions = [{**_dimension_dict(r), "modified_at": modified} for r in filtered]
    if page is None and page_size is None and not search and not sort and not order:
        return {"dimensions": dimensions}
    return {"dimensions": dimensions, "total": total, "page": page or 1, "page_size": page_size or total}


@router.post("/versions/{version_id}/dimensions")
def create_dimension(
    version_id: uuid.UUID,
    body: DimensionCreateRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        row = svc.create_dimension(version_id, workspace_id=ws, project_id=proj, data=body.model_dump())
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {"dimension": _dimension_dict(row)}


@router.patch("/versions/{version_id}/dimensions/{dimension_id}")
def patch_dimension(
    version_id: uuid.UUID,
    dimension_id: uuid.UUID,
    body: DimensionUpdateRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        row = svc.update_dimension(
            version_id,
            dimension_id,
            workspace_id=ws,
            project_id=proj,
            data=body.model_dump(exclude_unset=True),
        )
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {"dimension": _dimension_dict(row)}


@router.delete("/versions/{version_id}/dimensions/{dimension_id}")
def delete_dimension(
    version_id: uuid.UUID,
    dimension_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        svc.delete_dimension(version_id, dimension_id, workspace_id=ws, project_id=proj)
        session.commit()
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {"deleted": True}


@router.post("/versions/{version_id}/dimensions/bulk-delete", response_model=BulkDeleteResponse)
def bulk_delete_dimensions(
    version_id: uuid.UUID,
    body: SemanticBulkDeleteRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticBulkDeleteService(session, get_settings())
    try:
        return svc.delete_dimensions(version_id, body.ids, workspace_id=ws, project_id=proj)
    except SemanticRegistryError as exc:
        raise _err(exc) from exc


@router.get("/versions/{version_id}/relationships")
def list_relationships(
    version_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
    search: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    order: str | None = Query(default=None),
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=200),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        version = svc.get_version(version_id, workspace_id=ws, project_id=proj)
        rows = svc.list_relationships(version_id, workspace_id=ws, project_id=proj)
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    modified = version.updated_at.isoformat() if version.updated_at else None
    for row in rows:
        row.updated_at = version.updated_at  # type: ignore[attr-defined]
    filtered, total = apply_list_query(
        rows,
        search=search,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
        allowed_sort=_RELATIONSHIP_SORT,
        search_text=lambda r: " ".join(
            p for p in (r.name, r.key, r.from_entity_key, r.to_entity_key, r.join_expression, r.description) if p
        ),
    )
    relationships = [{**_relationship_dict(r), "modified_at": modified} for r in filtered]
    if page is None and page_size is None and not search and not sort and not order:
        return {"relationships": relationships}
    return {"relationships": relationships, "total": total, "page": page or 1, "page_size": page_size or total}


@router.post("/versions/{version_id}/relationships")
def create_relationship(
    version_id: uuid.UUID,
    body: RelationshipCreateRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        row = svc.create_relationship(version_id, workspace_id=ws, project_id=proj, data=body.model_dump())
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {"relationship": _relationship_dict(row)}


@router.patch("/versions/{version_id}/relationships/{relationship_id}")
def patch_relationship(
    version_id: uuid.UUID,
    relationship_id: uuid.UUID,
    body: RelationshipUpdateRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        row = svc.update_relationship(
            version_id,
            relationship_id,
            workspace_id=ws,
            project_id=proj,
            data=body.model_dump(exclude_unset=True),
        )
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {"relationship": _relationship_dict(row)}


@router.delete("/versions/{version_id}/relationships/{relationship_id}")
def delete_relationship(
    version_id: uuid.UUID,
    relationship_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        svc.delete_relationship(version_id, relationship_id, workspace_id=ws, project_id=proj)
        session.commit()
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {"deleted": True}


@router.post("/versions/{version_id}/relationships/bulk-delete", response_model=BulkDeleteResponse)
def bulk_delete_relationships(
    version_id: uuid.UUID,
    body: SemanticBulkDeleteRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticBulkDeleteService(session, get_settings())
    try:
        return svc.delete_relationships(version_id, body.ids, workspace_id=ws, project_id=proj)
    except SemanticRegistryError as exc:
        raise _err(exc) from exc


@router.get("/versions/{version_id}/terms")
def list_terms(
    version_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
    search: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    order: str | None = Query(default=None),
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=200),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        version = svc.get_version(version_id, workspace_id=ws, project_id=proj)
        rows = svc.list_terms(version_id, workspace_id=ws, project_id=proj)
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    modified = version.updated_at.isoformat() if version.updated_at else None
    for row in rows:
        row.updated_at = version.updated_at  # type: ignore[attr-defined]
    filtered, total = apply_list_query(
        rows,
        search=search,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
        allowed_sort=_TERM_SORT,
        search_text=lambda r: " ".join(p for p in (r.term, r.key, r.definition, *(r.synonyms or [])) if p),
    )
    terms = [{**_term_dict(r), "modified_at": modified} for r in filtered]
    if page is None and page_size is None and not search and not sort and not order:
        return {"terms": terms}
    return {"terms": terms, "total": total, "page": page or 1, "page_size": page_size or total}


@router.post("/versions/{version_id}/terms")
def create_term(
    version_id: uuid.UUID,
    body: TermCreateRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        row = svc.create_term(version_id, workspace_id=ws, project_id=proj, data=body.model_dump())
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {"term": _term_dict(row)}


@router.patch("/versions/{version_id}/terms/{term_id}")
def patch_term(
    version_id: uuid.UUID,
    term_id: uuid.UUID,
    body: TermUpdateRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        row = svc.update_term(
            version_id,
            term_id,
            workspace_id=ws,
            project_id=proj,
            data=body.model_dump(exclude_unset=True),
        )
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {"term": _term_dict(row)}


@router.delete("/versions/{version_id}/terms/{term_id}")
def delete_term(
    version_id: uuid.UUID,
    term_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        svc.delete_term(version_id, term_id, workspace_id=ws, project_id=proj)
        session.commit()
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    return {"deleted": True}


@router.post("/versions/{version_id}/terms/bulk-delete", response_model=BulkDeleteResponse)
def bulk_delete_terms(
    version_id: uuid.UUID,
    body: SemanticBulkDeleteRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticBulkDeleteService(session, get_settings())
    try:
        return svc.delete_terms(version_id, body.ids, workspace_id=ws, project_id=proj)
    except SemanticRegistryError as exc:
        raise _err(exc) from exc


class _RecentDefinitionRow:
    __slots__ = ("object_id", "object_kind", "name", "type", "definition", "source", "status", "updated_at", "created_at", "key")

    def __init__(self, **fields):
        for k in self.__slots__:
            setattr(self, k, fields.get(k))


@router.get("/versions/{version_id}/recent-definitions")
def list_recent_definitions(
    version_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
    search: str | None = Query(default=None),
    object_type: str | None = Query(default=None, alias="type"),
    sort: str | None = Query(default=None),
    order: str | None = Query(default=None),
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=200),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        version = svc.get_version(version_id, workspace_id=ws, project_id=proj)
        metrics = svc.list_metrics(version_id, workspace_id=ws, project_id=proj)
        dimensions = svc.list_dimensions(version_id, workspace_id=ws, project_id=proj)
        relationships = svc.list_relationships(version_id, workspace_id=ws, project_id=proj)
        terms = svc.list_terms(version_id, workspace_id=ws, project_id=proj)
    except SemanticRegistryError as exc:
        raise _err(exc) from exc
    modified = version.updated_at
    rows: list[_RecentDefinitionRow] = []
    for m in metrics:
        rows.append(
            _RecentDefinitionRow(
                object_id=str(m.id),
                object_kind="metric",
                key=m.key,
                name=m.name,
                type="Metric",
                definition=m.business_definition or m.description or "",
                source=m.source_entity_key,
                status="Ready",
                updated_at=modified,
                created_at=None,
            )
        )
    for d in dimensions:
        rows.append(
            _RecentDefinitionRow(
                object_id=str(d.id),
                object_kind="dimension",
                key=d.key,
                name=d.name,
                type="Dimension",
                definition=d.description or "",
                source=f"{d.source_entity_key}.{d.source_column}",
                status="Ready",
                updated_at=modified,
                created_at=None,
            )
        )
    for r in relationships:
        rows.append(
            _RecentDefinitionRow(
                object_id=str(r.id),
                object_kind="relationship",
                key=r.key,
                name=r.name,
                type="Relationship",
                definition=r.description or "",
                source=f"{r.from_entity_key} → {r.to_entity_key}",
                status="Ready",
                updated_at=modified,
                created_at=None,
            )
        )
    for t in terms:
        rows.append(
            _RecentDefinitionRow(
                object_id=str(t.id),
                object_kind="glossary",
                key=t.key,
                name=t.term,
                type="Glossary",
                definition=t.definition or "",
                source="—",
                status="Ready",
                updated_at=modified,
                created_at=None,
            )
        )
    type_filter = (object_type or "").strip().casefold()
    if type_filter:
        rows = [r for r in rows if r.type.casefold() == type_filter or r.object_kind == type_filter]
    filtered, total = apply_list_query(
        rows,
        search=search,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
        allowed_sort=_RECENT_SORT,
        search_text=lambda r: " ".join(p for p in (r.name, r.type, r.definition, r.source, r.key) if p),
    )
    items = [
        {
            "object_id": r.object_id,
            "object_kind": r.object_kind,
            "name": r.name,
            "type": r.type,
            "definition": r.definition,
            "source": r.source,
            "status": r.status,
            "modified_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in filtered
    ]
    if page is None and page_size is None and not search and not sort and not order and not object_type:
        return {"definitions": items}
    return {"definitions": items, "total": total, "page": page or 1, "page_size": page_size or total}


@router.get("/import/source")
def ossie_import_source(session: Session = Depends(postgres_session), ctx=Depends(default_project_context)):
    _ctx_ids(ctx)
    return SemanticRegistryService(session).ossie_import_source()


@router.post("/import")
def import_ossie(
    body: OssieImportRequest,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = SemanticRegistryService(session)
    try:
        return svc.import_from_ossie(
            workspace_id=ws,
            project_id=proj,
            model_key=body.model_key,
            model_name=body.model_name,
            dry_run=body.dry_run,
        )
    except SemanticRegistryError as exc:
        raise _err(exc) from exc


def _runtime_service(session: Session, request: Request) -> SemanticRuntimeService:
    return SemanticRuntimeService(session, settings=request.app.state.settings)


@router.get("/runtime/status")
def runtime_status(
    request: Request,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
    model_key: str | None = Query(None),
):
    ws, proj = _ctx_ids(ctx)
    svc = _runtime_service(session, request)
    return svc.runtime_status(workspace_id=ws, project_id=proj, model_key=model_key)


@router.get("/runtime/deployments")
def list_runtime_deployments(
    request: Request,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
    model_key: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    ws, proj = _ctx_ids(ctx)
    svc = _runtime_service(session, request)
    rows = svc.list_deployments(workspace_id=ws, project_id=proj, model_key=model_key, limit=limit)
    return {"deployments": [SemanticRuntimeService._deployment_dict(r) for r in rows]}


@router.get("/runtime/deployments/{deployment_id}")
def get_runtime_deployment(
    deployment_id: uuid.UUID,
    request: Request,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = _runtime_service(session, request)
    try:
        return svc.get_deployment_detail(deployment_id, workspace_id=ws, project_id=proj)
    except SemanticRuntimeError as exc:
        raise _runtime_err(exc) from exc


@router.post("/versions/{version_id}/runtime/stage")
def stage_runtime_version(
    version_id: uuid.UUID,
    request: Request,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = _runtime_service(session, request)
    try:
        dep = svc.stage_version(version_id, workspace_id=ws, project_id=proj)
        return {"deployment": SemanticRuntimeService._deployment_dict(dep)}
    except SemanticRuntimeError as exc:
        raise _runtime_err(exc) from exc


@router.post("/runtime/deployments/{deployment_id}/validate")
def validate_runtime_deployment(
    deployment_id: uuid.UUID,
    request: Request,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = _runtime_service(session, request)
    try:
        return svc.validate_deployment(deployment_id, workspace_id=ws, project_id=proj)
    except SemanticRuntimeError as exc:
        raise _runtime_err(exc) from exc


@router.post("/runtime/deployments/{deployment_id}/smoke")
def smoke_runtime_deployment(
    deployment_id: uuid.UUID,
    request: Request,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = _runtime_service(session, request)
    try:
        return svc.smoke_deployment(deployment_id, workspace_id=ws, project_id=proj)
    except SemanticRuntimeError as exc:
        raise _runtime_err(exc) from exc


@router.post("/runtime/deployments/{deployment_id}/activate")
def activate_runtime_deployment(
    deployment_id: uuid.UUID,
    request: Request,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
    dry_run: bool = Query(False),
):
    ws, proj = _ctx_ids(ctx)
    svc = _runtime_service(session, request)
    try:
        result = svc.activate_deployment(
            deployment_id,
            workspace_id=ws,
            project_id=proj,
            dry_run=dry_run,
        )
        if not dry_run and result.get("result") in {"ACTIVATED", "ALREADY_ACTIVE"}:
            from app.db.platform_models import SemanticModelRow, SemanticRuntimeDeploymentRow

            loader = SemanticRuntimeLoader.get(request.app.state.settings)
            deployment = session.get(SemanticRuntimeDeploymentRow, deployment_id)
            model_key: str | None = None
            if deployment is not None:
                model = session.get(SemanticModelRow, deployment.semantic_model_id)
                if model is not None:
                    model_key = model.key
            bundle = loader.refresh(
                session,
                workspace_id=ws,
                project_id=proj,
                model_key=model_key,
            )
            request.app.state.chat_service.apply_runtime_bundle(bundle)
        return result
    except SemanticRuntimeError as exc:
        raise _runtime_err(exc) from exc


@router.post("/runtime/deployments/{deployment_id}/rollback")
def rollback_runtime_deployment(
    deployment_id: uuid.UUID,
    request: Request,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
):
    ws, proj = _ctx_ids(ctx)
    svc = _runtime_service(session, request)
    try:
        result = svc.rollback_deployment(deployment_id, workspace_id=ws, project_id=proj)
        request.app.state.chat_service.apply_runtime_bundle(
            SemanticRuntimeLoader.get(request.app.state.settings).get_bundle()
        )
        return result
    except SemanticRuntimeError as exc:
        raise _runtime_err(exc) from exc
