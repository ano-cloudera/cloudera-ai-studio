from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.models import AskDataRequest, ChatContextSource
from app.rag.scope import resolve_library_ids
from app.services.chat_attachment_service import ChatAttachmentService, ChatAttachmentServiceError


class ContextSourceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def knowledge_library_sources(sources: list[ChatContextSource] | None) -> list[ChatContextSource]:
    if not sources:
        return []
    return [item for item in sources if item.type == "knowledge_library"]


def uploaded_file_sources(sources: list[ChatContextSource] | None) -> list[ChatContextSource]:
    if not sources:
        return []
    return [item for item in sources if item.type == "uploaded_file"]


def structured_data_sources(sources: list[ChatContextSource] | None) -> list[ChatContextSource]:
    if not sources:
        return []
    structured = {"table", "semantic_model", "semantic_entity", "semantic_metric", "semantic_term"}
    return [item for item in sources if item.type in structured]


def apply_context_sources(
    request: AskDataRequest,
    *,
    session: Session,
    project_id: uuid.UUID,
    conversation_history: list[dict],
    settings,
) -> AskDataRequest:
    libs = knowledge_library_sources(request.context_sources)
    files = uploaded_file_sources(request.context_sources)
    structured = structured_data_sources(request.context_sources)

    if sum(bool(x) for x in (libs, files, structured)) > 1:
        raise ContextSourceError(
            "mixed_context_unsupported",
            "Use one context family per request: Knowledge, uploaded files, or structured data (@ table/metric/semantic).",
            422,
        )

    if structured:
        return request

    if not libs and not files:
        return request

    if request.mode == "rag" and (request.library_ids or request.rag_document_ids):
        return request

    if files:
        attachment_ids: list[uuid.UUID] = []
        for item in files:
            raw = (item.id or "").strip()
            if not raw:
                raise ContextSourceError("invalid_context", "Uploaded file context is missing an id", 422)
            try:
                attachment_ids.append(uuid.UUID(raw))
            except ValueError as exc:
                raise ContextSourceError("invalid_context", "Attachment id is not valid", 422) from exc
        service = ChatAttachmentService(settings, session)
        try:
            doc_ids = service.resolve_ready_document_ids(attachment_ids, project_id=project_id)
        except ChatAttachmentServiceError as exc:
            raise ContextSourceError(exc.code, exc.message, exc.status_code) from exc
        return request.model_copy(
            update={
                "mode": "rag",
                "library_ids": None,
                "rag_document_ids": [str(item) for item in doc_ids],
            }
        )

    parsed: list[uuid.UUID] = []
    for item in libs:
        raw = (item.id or "").strip()
        if not raw:
            raise ContextSourceError("invalid_context", "Knowledge library context is missing an id", 422)
        try:
            parsed.append(uuid.UUID(raw))
        except ValueError as exc:
            raise ContextSourceError("invalid_context", "Knowledge library id is not valid", 422) from exc
    unique = list(dict.fromkeys(parsed))

    scoped = resolve_library_ids(
        session,
        project_id=project_id,
        requested=[str(item) for item in unique],
        history=conversation_history,
        default_library_ids=[],
    )
    if set(scoped) != set(unique):
        raise ContextSourceError(
            "library_not_found",
            "One or more knowledge libraries were not found or are not accessible",
            404,
        )

    return request.model_copy(
        update={
            "mode": "rag",
            "library_ids": [str(item) for item in scoped],
            "rag_document_ids": None,
        }
    )


def context_source_http_error(exc: ContextSourceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})
