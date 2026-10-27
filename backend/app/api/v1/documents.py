from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.v1.deps import default_project_context, postgres_session, require_postgres_settings
from app.api.v1.project_scope import assert_document_scope
from app.core.config import Settings
from app.documents.batch_upload import BatchFileInput, RejectedBatchItem, validate_file_batch
from app.documents.bulk_schemas import BulkDeleteDocumentsRequest, BulkDeleteResponse
from app.documents.schemas import DocumentRename, DocumentResponse
from app.documents.validation import parse_allowed_types
from app.services.bulk_delete_service import BulkDeleteService, BulkDeleteServiceError
from app.jobs.document_runner import build_document_job_runner
from app.services.document_service import DocumentService, DocumentServiceError

router = APIRouter(tags=["documents"])


def _document_service(settings: Settings, session: Session) -> DocumentService:
    return DocumentService(settings, session)


def _handle_document_error(exc: DocumentServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


def _handle_bulk_error(exc: BulkDeleteServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


def _public_document(doc: DocumentResponse) -> dict:
    payload = doc.model_dump(mode="json")
    payload.pop("storage_path", None)
    meta = payload.pop("metadata", None) or {}
    payload["processing_stage"] = meta.get("processing_stage")
    payload["error_summary"] = meta.get("error_summary")
    payload["chunk_count"] = meta.get("chunk_count")
    return payload


def _maybe_enqueue(settings: Settings, background_tasks: BackgroundTasks, document_id: uuid.UUID) -> None:
    if not settings.document_auto_process:
        return
    build_document_job_runner(settings).enqueue(background_tasks, document_id)


@router.post("/libraries/{library_id}/documents")
async def upload_document(
    library_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    session: Session = Depends(postgres_session),
    settings: Settings = Depends(require_postgres_settings),
    file: UploadFile = File(...),
) -> dict:
    data = await file.read()
    filename = file.filename or "upload"
    service = _document_service(settings, session)
    try:
        document = service.upload_document(library_id=library_id, filename=filename, data=data)
    except DocumentServiceError as exc:
        raise _handle_document_error(exc) from exc
    _maybe_enqueue(settings, background_tasks, document.id)
    return {"document": _public_document(document)}


@router.post("/libraries/{library_id}/documents/batch-upload")
async def batch_upload_documents(
    library_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    session: Session = Depends(postgres_session),
    settings: Settings = Depends(require_postgres_settings),
    ctx=Depends(default_project_context),
    files: list[UploadFile] = File(...),
) -> dict:
    _, project_id = ctx
    service = _document_service(settings, session)
    try:
        library = service.get_library_for_project(library_id, project_id)
    except DocumentServiceError as exc:
        raise _handle_document_error(exc) from exc

    inputs: list[BatchFileInput] = []
    for upload in files:
        data = await upload.read()
        inputs.append(BatchFileInput(filename=upload.filename or "upload", data=data))

    max_file_bytes = int(settings.document_max_file_mb) * 1024 * 1024
    batch = validate_file_batch(
        inputs,
        max_files=int(settings.knowledge_upload_max_files_per_batch),
        max_file_bytes=max_file_bytes,
        max_batch_bytes=int(settings.knowledge_upload_max_batch_mb) * 1024 * 1024,
        allowed_types=parse_allowed_types(settings.document_allowed_types),
    )
    if batch.rejected and not batch.accepted and batch.rejected[0].filename == "":
        item = batch.rejected[0]
        raise HTTPException(status_code=400, detail={"code": item.code, "message": item.message})

    limit = int(settings.knowledge_max_documents_per_library)
    current = service._document_count(library_id)  # noqa: SLF001
    remaining = max(0, limit - current)
    if remaining <= 0:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "LIBRARY_DOCUMENT_LIMIT_REACHED",
                "message": f"This library can accept 0 more documents.",
            },
        )
    if len(batch.accepted) > remaining:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "LIBRARY_DOCUMENT_LIMIT_REACHED",
                "message": f"This library can accept {remaining} more document(s).",
                "remaining_capacity": remaining,
            },
        )

    accepted_docs = []
    rejected_items = list(batch.rejected)
    for item in batch.accepted:
        try:
            document = service.upload_document(library_id=library.id, filename=item.filename, data=item.data)
        except DocumentServiceError as exc:
            rejected_items.append(
                RejectedBatchItem(filename=item.filename, code=exc.code, message=exc.message),
            )
            continue
        _maybe_enqueue(settings, background_tasks, document.id)
        accepted_docs.append(_public_document(document))

    rejected = [{"filename": r.filename, "code": r.code, "message": r.message} for r in rejected_items]
    return {"requested": len(inputs), "accepted": accepted_docs, "rejected": rejected}


@router.get("/libraries/{library_id}/documents")
def list_library_documents(
    library_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    settings: Settings = Depends(require_postgres_settings),
    page: int | None = Query(None, ge=1),
    page_size: int | None = Query(None, ge=1, le=100),
    search: str | None = Query(None),
    status: str | None = Query(None),
    sort: str | None = Query(None),
    order: str | None = Query(None),
) -> dict:
    service = _document_service(settings, session)
    try:
        if page is not None or page_size is not None or search or status or sort or order:
            sort_field = sort if sort in {
                "original_filename",
                "mime_type",
                "size_bytes",
                "chunk_count",
                "status",
                "created_at",
                "updated_at",
            } else "updated_at"
            sort_order = order if order in {"asc", "desc"} else "desc"
            result = service.list_documents_paginated(
                library_id,
                page=page or 1,
                page_size=page_size or 10,
                search=search,
                status=status,
                sort=sort_field,
                order=sort_order,
            )
            return {
                "items": [_public_document(doc) for doc in result.items],
                "page": result.page,
                "page_size": result.page_size,
                "total": result.total,
                "total_pages": result.total_pages,
            }
        documents = service.list_documents(library_id)
    except DocumentServiceError as exc:
        raise _handle_document_error(exc) from exc
    return {"documents": [_public_document(doc) for doc in documents]}


@router.post("/documents/bulk-delete")
def bulk_delete_documents(
    body: BulkDeleteDocumentsRequest,
    session: Session = Depends(postgres_session),
    settings: Settings = Depends(require_postgres_settings),
    ctx=Depends(default_project_context),
) -> dict:
    _, project_id = ctx
    if len(body.ids) > settings.bulk_delete_max_items:
        raise _handle_bulk_error(
            BulkDeleteServiceError(
                "BULK_DELETE_LIMIT_EXCEEDED",
                f"No more than {settings.bulk_delete_max_items} items may be deleted at once",
                422,
            )
        )
    service = BulkDeleteService(session, settings)
    result = service.delete_documents(
        body.ids,
        project_id=project_id,
        library_id=body.library_id,
    )
    return result.model_dump(mode="json")


@router.get("/documents/{document_id}")
def get_document(
    document_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    settings: Settings = Depends(require_postgres_settings),
    ctx=Depends(default_project_context),
) -> dict:
    _, project_id = ctx
    service = _document_service(settings, session)
    try:
        row = service.get_document(document_id)
        assert_document_scope(row, project_id=project_id)
    except DocumentServiceError as exc:
        raise _handle_document_error(exc) from exc
    return {"document": _public_document(DocumentResponse.from_row(row))}


@router.patch("/documents/{document_id}")
def rename_document(
    document_id: uuid.UUID,
    body: DocumentRename,
    session: Session = Depends(postgres_session),
    settings: Settings = Depends(require_postgres_settings),
    ctx=Depends(default_project_context),
) -> dict:
    _, project_id = ctx
    service = _document_service(settings, session)
    try:
        row = service.get_document(document_id)
        assert_document_scope(row, project_id=project_id)
        document = service.rename_document(document_id, body)
    except DocumentServiceError as exc:
        raise _handle_document_error(exc) from exc
    return {"document": _public_document(document)}


@router.post("/documents/{document_id}/process")
def process_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    session: Session = Depends(postgres_session),
    settings: Settings = Depends(require_postgres_settings),
) -> dict:
    service = _document_service(settings, session)
    try:
        row = service.queue_reprocess(document_id)
    except DocumentServiceError as exc:
        raise _handle_document_error(exc) from exc
    build_document_job_runner(settings).enqueue(background_tasks, row.id)
    return {"document": _public_document(DocumentResponse.from_row(row))}


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    settings: Settings = Depends(require_postgres_settings),
    ctx=Depends(default_project_context),
) -> dict:
    _, project_id = ctx
    service = _document_service(settings, session)
    try:
        row = service.get_document(document_id)
        assert_document_scope(row, project_id=project_id)
        service.delete_document(document_id)
    except DocumentServiceError as exc:
        raise _handle_document_error(exc) from exc
    return {"deleted": True, "document_id": str(document_id)}
