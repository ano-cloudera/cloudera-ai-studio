from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat.attachments.constants import (
    ATTACHMENT_STATUS_EXPIRED,
    ATTACHMENT_STATUS_FAILED,
    ATTACHMENT_STATUS_PROCESSING,
    ATTACHMENT_STATUS_READY,
    ATTACHMENT_STATUS_UPLOADING,
    CHAT_ATTACHMENTS_LIBRARY_NAME,
    CHAT_ATTACHMENT_ALLOWED_EXTENSIONS,
)
from app.chat.attachments.schemas import ChatAttachmentResponse
from app.core.config import Settings
from app.db.platform_models import ChatAttachmentRow, DocumentRow, LibraryRow, ProjectRow
from app.documents.batch_upload import AcceptedBatchItem, BatchFileInput, BatchValidationResult, validate_file_batch
from app.documents.schemas import LibraryCreate
from app.services.document_service import DocumentService, DocumentServiceError
from app.services.library_service import LibraryService, LibraryServiceError

logger = logging.getLogger(__name__)


class ChatAttachmentServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _allowed_chat_types() -> set[str]:
    return set(CHAT_ATTACHMENT_ALLOWED_EXTENSIONS)


class ChatAttachmentService:
    def __init__(self, settings: Settings, session: Session) -> None:
        self._settings = settings
        self._session = session

    def _max_file_bytes(self) -> int:
        return int(self._settings.chat_attachment_max_file_mb) * 1024 * 1024

    def _max_batch_bytes(self) -> int:
        return int(self._settings.chat_attachment_max_batch_mb) * 1024 * 1024

    def _ttl_days(self) -> int:
        return int(self._settings.chat_attachment_ttl_days)

    def ensure_hidden_library(self, *, workspace_id: uuid.UUID, project_id: uuid.UUID) -> LibraryRow:
        row = self._session.execute(
            select(LibraryRow).where(
                LibraryRow.project_id == project_id,
                LibraryRow.name == CHAT_ATTACHMENTS_LIBRARY_NAME,
            )
        ).scalar_one_or_none()
        if row:
            return row
        project = self._session.get(ProjectRow, project_id)
        if not project or project.workspace_id != workspace_id:
            raise ChatAttachmentServiceError("project_not_found", "Project not found", 404)
        now = _utcnow()
        row = LibraryRow(
            workspace_id=workspace_id,
            project_id=project_id,
            name=CHAT_ATTACHMENTS_LIBRARY_NAME,
            description="System library for temporary chat attachments",
            status="system",
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def _map_document_status(self, doc: DocumentRow | None) -> str:
        if not doc:
            return ATTACHMENT_STATUS_PROCESSING
        status = (doc.status or "").upper()
        if status == "READY":
            return ATTACHMENT_STATUS_READY
        if status == "FAILED":
            return ATTACHMENT_STATUS_FAILED
        return ATTACHMENT_STATUS_PROCESSING

    def _sync_from_document(self, row: ChatAttachmentRow) -> ChatAttachmentRow:
        if row.status == ATTACHMENT_STATUS_UPLOADING:
            return row
        if row.expires_at <= _utcnow():
            row.status = ATTACHMENT_STATUS_EXPIRED
            return row
        if not row.document_id:
            return row
        doc = self._session.get(DocumentRow, row.document_id)
        mapped = self._map_document_status(doc)
        if mapped == ATTACHMENT_STATUS_FAILED and doc:
            meta = doc.metadata_json or {}
            row.error_code = meta.get("error_code") or "PROCESSING_FAILED"
            row.error_message = meta.get("error_summary") or "Processing failed."
        elif mapped == ATTACHMENT_STATUS_READY:
            row.error_code = None
            row.error_message = None
        row.status = mapped
        row.updated_at = _utcnow()
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def to_response(self, row: ChatAttachmentRow) -> ChatAttachmentResponse:
        row = self._sync_from_document(row)
        meta = row.metadata_json or {}
        doc_meta: dict = {}
        if row.document_id:
            doc = self._session.get(DocumentRow, row.document_id)
            if doc and doc.metadata_json:
                doc_meta = doc.metadata_json
        return ChatAttachmentResponse(
            id=row.id,
            session_id=row.session_id,
            filename=row.filename,
            display_name=row.display_name,
            mime_type=row.mime_type,
            size_bytes=row.size_bytes,
            status=row.status,
            processing_type=row.processing_type,
            error_code=row.error_code,
            error_message=row.error_message,
            document_id=row.document_id,
            chunk_count=doc_meta.get("chunk_count"),
            page_count=doc_meta.get("page_count"),
            created_at=row.created_at,
            updated_at=row.updated_at,
            expires_at=row.expires_at,
        )

    def get_attachment(self, attachment_id: uuid.UUID, *, project_id: uuid.UUID) -> ChatAttachmentRow:
        row = self._session.get(ChatAttachmentRow, attachment_id)
        if not row or row.project_id != project_id:
            raise ChatAttachmentServiceError("not_found", "Attachment not found", 404)
        return row

    def validate_batch(self, files: list[BatchFileInput]) -> BatchValidationResult:
        return validate_file_batch(
            files,
            max_files=int(self._settings.chat_attachment_max_files),
            max_file_bytes=self._max_file_bytes(),
            max_batch_bytes=self._max_batch_bytes(),
            allowed_types=_allowed_chat_types(),
        )

    def create_from_accepted(
        self,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        session_id: str,
        item: AcceptedBatchItem,
    ) -> ChatAttachmentRow:
        library = self.ensure_hidden_library(workspace_id=workspace_id, project_id=project_id)
        docs = DocumentService(self._settings, self._session)
        try:
            document = docs.upload_document(library_id=library.id, filename=item.filename, data=item.data)
        except DocumentServiceError as exc:
            raise ChatAttachmentServiceError(exc.code, exc.message, exc.status_code) from exc

        doc_row = self._session.get(DocumentRow, document.id)
        if doc_row:
            meta = dict(doc_row.metadata_json or {})
            meta["source_type"] = "chat_attachment"
            doc_row.metadata_json = meta
            self._session.add(doc_row)

        now = _utcnow()
        attachment_id = uuid.uuid4()
        if doc_row:
            meta = dict(doc_row.metadata_json or {})
            meta["attachment_id"] = str(attachment_id)
            doc_row.metadata_json = meta
            self._session.add(doc_row)

        row = ChatAttachmentRow(
            id=attachment_id,
            workspace_id=workspace_id,
            project_id=project_id,
            session_id=session_id.strip() or "default",
            filename=item.filename,
            display_name=item.filename,
            mime_type=item.mime_type,
            size_bytes=item.size_bytes,
            storage_path=doc_row.storage_path if doc_row else "",
            document_id=document.id,
            status=ATTACHMENT_STATUS_PROCESSING,
            processing_type="unstructured",
            metadata_json={},
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(days=self._ttl_days()),
        )
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def delete_attachment(self, attachment_id: uuid.UUID, *, project_id: uuid.UUID) -> None:
        row = self.get_attachment(attachment_id, project_id=project_id)
        doc_id = row.document_id
        self._session.delete(row)
        self._session.commit()
        if doc_id:
            docs = DocumentService(self._settings, self._session)
            try:
                docs.delete_document(doc_id)
            except DocumentServiceError as exc:
                if exc.status_code != 404:
                    raise ChatAttachmentServiceError(exc.code, exc.message, exc.status_code) from exc

    def retry_attachment(self, attachment_id: uuid.UUID, *, project_id: uuid.UUID) -> ChatAttachmentRow:
        row = self.get_attachment(attachment_id, project_id=project_id)
        if not row.document_id:
            raise ChatAttachmentServiceError("invalid_state", "Attachment has no linked document", 422)
        docs = DocumentService(self._settings, self._session)
        docs.queue_reprocess(row.document_id)
        row.status = ATTACHMENT_STATUS_PROCESSING
        row.error_code = None
        row.error_message = None
        row.updated_at = _utcnow()
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def resolve_ready_document_ids(
        self,
        attachment_ids: list[uuid.UUID],
        *,
        project_id: uuid.UUID,
    ) -> list[uuid.UUID]:
        doc_ids: list[uuid.UUID] = []
        for aid in attachment_ids:
            row = self.get_attachment(aid, project_id=project_id)
            row = self._sync_from_document(row)
            if row.status == ATTACHMENT_STATUS_EXPIRED:
                raise ChatAttachmentServiceError(
                    "ATTACHMENT_EXPIRED",
                    "One or more attachments have expired.",
                    410,
                )
            if row.status != ATTACHMENT_STATUS_READY or not row.document_id:
                raise ChatAttachmentServiceError(
                    "attachment_not_ready",
                    "Wait until attached files finish processing.",
                    422,
                )
            doc_ids.append(row.document_id)
        return list(dict.fromkeys(doc_ids))

    def save_to_knowledge(
        self,
        attachment_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        library_id: uuid.UUID | None,
        new_library_name: str | None,
    ) -> dict:
        row = self.get_attachment(attachment_id, project_id=project_id)
        row = self._sync_from_document(row)
        if row.status != ATTACHMENT_STATUS_READY or not row.document_id:
            raise ChatAttachmentServiceError("attachment_not_ready", "Attachment is not ready to save", 422)

        meta = dict(row.metadata_json or {})
        if meta.get("saved_document_id") and meta.get("saved_library_id"):
            return {
                "library_id": str(meta["saved_library_id"]),
                "document_id": str(meta["saved_document_id"]),
                "attachment_id": str(row.id),
                "already_saved": True,
            }

        libs = LibraryService(self._session, document_limit=self._settings.knowledge_max_documents_per_library)
        target_library_id = library_id
        if not target_library_id:
            name = (new_library_name or "").strip()
            if not name:
                raise ChatAttachmentServiceError("invalid_library", "Choose a library or provide a new name", 422)
            try:
                created = libs.create_library(
                    workspace_id=workspace_id,
                    project_id=project_id,
                    body=LibraryCreate(name=name, project_id=project_id),
                )
            except LibraryServiceError as exc:
                raise ChatAttachmentServiceError(exc.code, exc.message, exc.status_code) from exc
            target_library_id = created.id

        source_doc = self._session.get(DocumentRow, row.document_id)
        if not source_doc:
            raise ChatAttachmentServiceError("not_found", "Source document missing", 404)

        store = DocumentService(self._settings, self._session)._store
        try:
            data = store.get(source_doc.storage_path)
        except Exception as exc:
            raise ChatAttachmentServiceError("storage_read_failed", "Could not read attachment file", 500) from exc

        docs = DocumentService(self._settings, self._session)
        try:
            promoted = docs.upload_document(
                library_id=target_library_id,
                filename=row.display_name,
                data=data,
            )
        except DocumentServiceError as exc:
            raise ChatAttachmentServiceError(exc.code, exc.message, exc.status_code) from exc

        meta["saved_library_id"] = str(target_library_id)
        meta["saved_document_id"] = str(promoted.id)
        row.metadata_json = meta
        row.updated_at = _utcnow()
        self._session.add(row)
        self._session.commit()

        return {
            "library_id": str(target_library_id),
            "document_id": str(promoted.id),
            "attachment_id": str(row.id),
        }
