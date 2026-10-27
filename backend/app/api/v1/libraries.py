from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import default_project_context, postgres_session, require_postgres_settings
from app.api.v1.project_scope import assert_library_scope
from app.core.config import Settings
from app.documents.bulk_schemas import BulkDeleteLibrariesRequest, BulkDeleteResponse
from app.documents.schemas import LibraryCreate, LibraryRename, LibraryResponse, LibraryUpdate
from app.services.bulk_delete_service import BulkDeleteService, BulkDeleteServiceError
from app.services.library_service import LibraryService, LibraryServiceError

router = APIRouter(prefix="/libraries", tags=["libraries"])


def _library_service(session: Session, settings: Settings) -> LibraryService:
    return LibraryService(session, document_limit=settings.knowledge_max_documents_per_library)


def _handle_library_error(exc: LibraryServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


def _handle_bulk_error(exc: BulkDeleteServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


def _library_payload(lib) -> dict:
    data = lib.model_dump(mode="json")
    return data


@router.post("", response_model=dict)
def create_library(
    body: LibraryCreate,
    session: Session = Depends(postgres_session),
    settings: Settings = Depends(require_postgres_settings),
    ctx=Depends(default_project_context),
) -> dict:
    workspace_id, default_project_id = ctx
    project_id = body.project_id or default_project_id
    if body.project_id and body.project_id != default_project_id:
        project_id = body.project_id
    service = _library_service(session, settings)
    try:
        library = service.create_library(workspace_id=workspace_id, project_id=project_id, body=body)
    except LibraryServiceError as exc:
        raise _handle_library_error(exc) from exc
    return {"library": _library_payload(library)}


@router.get("")
def list_libraries(
    session: Session = Depends(postgres_session),
    settings: Settings = Depends(require_postgres_settings),
    ctx=Depends(default_project_context),
    project_id: uuid.UUID | None = Query(None),
    page: int | None = Query(None, ge=1),
    page_size: int | None = Query(None, ge=1, le=100),
    search: str | None = Query(None),
    sort: str | None = Query(None),
    order: str | None = Query(None),
) -> dict:
    workspace_id, default_project_id = ctx
    pid = project_id or default_project_id
    service = _library_service(session, settings)
    if page is not None or page_size is not None or search or sort or order:
        sort_field = sort if sort in {"name", "updated_at", "created_at", "document_count"} else "updated_at"
        sort_order = order if order in {"asc", "desc"} else "desc"
        result = service.list_libraries_paginated(
            workspace_id=workspace_id,
            project_id=pid,
            page=page or 1,
            page_size=page_size or 10,
            search=search,
            sort=sort_field,  # type: ignore[arg-type]
            order=sort_order,  # type: ignore[arg-type]
        )
        return {
            "items": [_library_payload(item) for item in result.items],
            "page": result.page,
            "page_size": result.page_size,
            "total": result.total,
            "total_pages": result.total_pages,
        }
    libraries = service.list_libraries(workspace_id=workspace_id, project_id=pid)
    return {"libraries": [_library_payload(lib) for lib in libraries]}


@router.post("/bulk-delete")
def bulk_delete_libraries(
    body: BulkDeleteLibrariesRequest,
    session: Session = Depends(postgres_session),
    settings: Settings = Depends(require_postgres_settings),
    ctx=Depends(default_project_context),
) -> dict:
    workspace_id, project_id = ctx
    if len(body.ids) > settings.bulk_delete_max_items:
        raise _handle_bulk_error(
            BulkDeleteServiceError(
                "BULK_DELETE_LIMIT_EXCEEDED",
                f"No more than {settings.bulk_delete_max_items} items may be deleted at once",
                422,
            )
        )
    service = BulkDeleteService(session, settings)
    result = service.delete_libraries(body.ids, workspace_id=workspace_id, project_id=project_id)
    return result.model_dump(mode="json")


@router.get("/{library_id}")
def get_library(
    library_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    settings: Settings = Depends(require_postgres_settings),
    ctx=Depends(default_project_context),
) -> dict:
    ws, proj = ctx
    service = _library_service(session, settings)
    try:
        detail = service.get_library_detail(library_id)
        row = service.get_library(library_id)
        assert_library_scope(row, workspace_id=ws, project_id=proj)
    except LibraryServiceError as exc:
        raise _handle_library_error(exc) from exc
    return {"library": _library_payload(detail)}


@router.patch("/{library_id}")
def update_library(
    library_id: uuid.UUID,
    body: LibraryUpdate,
    session: Session = Depends(postgres_session),
    settings: Settings = Depends(require_postgres_settings),
    ctx=Depends(default_project_context),
) -> dict:
    ws, proj = ctx
    service = _library_service(session, settings)
    try:
        row = service.get_library(library_id)
        assert_library_scope(row, workspace_id=ws, project_id=proj)
        library = service.update_library(library_id, body)
    except LibraryServiceError as exc:
        raise _handle_library_error(exc) from exc
    return {"library": _library_payload(library)}


@router.delete("/{library_id}")
def delete_library(
    library_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    settings: Settings = Depends(require_postgres_settings),
    ctx=Depends(default_project_context),
) -> dict:
    ws, proj = ctx
    service = _library_service(session, settings)
    try:
        row = service.get_library(library_id)
        assert_library_scope(row, workspace_id=ws, project_id=proj)
        service.delete_library(library_id, settings=settings)
    except LibraryServiceError as exc:
        raise _handle_library_error(exc) from exc
    return {"deleted": True, "library_id": str(library_id)}
