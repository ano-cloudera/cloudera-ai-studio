from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.v1.deps import default_project_context, postgres_session, require_postgres_settings
from app.chat.attachments.schemas import SaveAttachmentToKnowledgeRequest
from app.core.config import Settings
from app.documents.batch_upload import BatchFileInput
from app.jobs.document_runner import build_document_job_runner
from app.services.chat_attachment_service import ChatAttachmentService, ChatAttachmentServiceError

router = APIRouter(prefix="/chat/attachments", tags=["chat-attachments"])


def _service(settings: Settings, session: Session) -> ChatAttachmentService:
    return ChatAttachmentService(settings, session)


def _handle_error(exc: ChatAttachmentServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


def _enqueue(settings: Settings, background_tasks: BackgroundTasks, document_id: uuid.UUID) -> None:
    if not settings.document_auto_process:
        return
    build_document_job_runner(settings).enqueue(background_tasks, document_id)


@router.post("/batch")
async def batch_upload_attachments(
    background_tasks: BackgroundTasks,
    session_id: str = Form(...),
    session: Session = Depends(postgres_session),
    settings: Settings = Depends(require_postgres_settings),
    ctx=Depends(default_project_context),
    files: list[UploadFile] = File(...),
) -> dict:
    workspace_id, project_id = ctx
    service = _service(settings, session)
    inputs: list[BatchFileInput] = []
    for upload in files:
        data = await upload.read()
        inputs.append(BatchFileInput(filename=upload.filename or "upload", data=data))

    batch = service.validate_batch(inputs)
    if batch.rejected and not batch.accepted and batch.rejected[0].filename == "":
        item = batch.rejected[0]
        raise HTTPException(status_code=400, detail={"code": item.code, "message": item.message})

    accepted_responses = []
    for item in batch.accepted:
        row = service.create_from_accepted(
            workspace_id=workspace_id,
            project_id=project_id,
            session_id=session_id,
            item=item,
        )
        if row.document_id:
            _enqueue(settings, background_tasks, row.document_id)
        accepted_responses.append(service.to_response(row).model_dump(mode="json"))

    rejected = [
        {"filename": r.filename, "code": r.code, "message": r.message} for r in batch.rejected
    ]
    return {
        "requested": len(inputs),
        "accepted": accepted_responses,
        "rejected": rejected,
    }


@router.get("/{attachment_id}")
def get_attachment(
    attachment_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    settings: Settings = Depends(require_postgres_settings),
    ctx=Depends(default_project_context),
) -> dict:
    _, project_id = ctx
    service = _service(settings, session)
    try:
        row = service.get_attachment(attachment_id, project_id=project_id)
    except ChatAttachmentServiceError as exc:
        raise _handle_error(exc) from exc
    return {"attachment": service.to_response(row).model_dump(mode="json")}


@router.post("/{attachment_id}/retry")
def retry_attachment(
    attachment_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    session: Session = Depends(postgres_session),
    settings: Settings = Depends(require_postgres_settings),
    ctx=Depends(default_project_context),
) -> dict:
    workspace_id, project_id = ctx
    service = _service(settings, session)
    try:
        row = service.retry_attachment(attachment_id, project_id=project_id)
    except ChatAttachmentServiceError as exc:
        raise _handle_error(exc) from exc
    if row.document_id:
        _enqueue(settings, background_tasks, row.document_id)
    return {"attachment": service.to_response(row).model_dump(mode="json")}


@router.delete("/{attachment_id}")
def delete_attachment(
    attachment_id: uuid.UUID,
    session: Session = Depends(postgres_session),
    settings: Settings = Depends(require_postgres_settings),
    ctx=Depends(default_project_context),
) -> dict:
    _, project_id = ctx
    service = _service(settings, session)
    try:
        service.delete_attachment(attachment_id, project_id=project_id)
    except ChatAttachmentServiceError as exc:
        raise _handle_error(exc) from exc
    return {"deleted": True, "id": str(attachment_id)}


@router.post("/{attachment_id}/save-to-knowledge")
def save_attachment_to_knowledge(
    attachment_id: uuid.UUID,
    body: SaveAttachmentToKnowledgeRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(postgres_session),
    settings: Settings = Depends(require_postgres_settings),
    ctx=Depends(default_project_context),
) -> dict:
    workspace_id, project_id = ctx
    service = _service(settings, session)
    try:
        result = service.save_to_knowledge(
            attachment_id,
            workspace_id=workspace_id,
            project_id=project_id,
            library_id=body.library_id,
            new_library_name=body.new_library_name,
        )
    except ChatAttachmentServiceError as exc:
        raise _handle_error(exc) from exc
    doc_id = uuid.UUID(result["document_id"])
    _enqueue(settings, background_tasks, doc_id)
    return {"saved": result}
