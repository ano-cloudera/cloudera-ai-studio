from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.chat.attachments.constants import CHAT_ATTACHMENTS_LIBRARY_NAME
from app.db.platform_models import DocumentRow, LibraryRow
from app.vectors.store import build_vector_store
from app.documents.pagination import PaginatedResponse, clamp_page, clamp_page_size, total_pages
from app.documents.schemas import DocumentRename, DocumentResponse
from app.documents.validation import UploadValidationError, sanitize_storage_filename, validate_upload
from app.storage.object_store import ObjectStore, ObjectStoreError, build_object_store

logger = logging.getLogger(__name__)


class DocumentServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def storage_key(
    *,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    library_id: uuid.UUID,
    document_id: uuid.UUID,
    stored_filename: str,
) -> str:
    return f"{workspace_id}/{project_id}/{library_id}/{document_id}/original/{stored_filename}"


class DocumentService:
    def __init__(self, settings: Settings, session: Session, object_store: ObjectStore | None = None) -> None:
        self._settings = settings
        self._session = session
        self._store = object_store or build_object_store(settings.document_storage_root)

    def _allowed_types(self) -> set[str]:
        from app.documents.validation import parse_allowed_types

        return parse_allowed_types(self._settings.document_allowed_types)

    def _max_bytes(self) -> int:
        return int(self._settings.document_max_file_mb) * 1024 * 1024

    def get_document(self, document_id: uuid.UUID) -> DocumentRow:
        row = self._session.get(DocumentRow, document_id)
        if not row:
            raise DocumentServiceError("not_found", "Document not found", 404)
        return row

    def get_library_for_project(self, library_id: uuid.UUID, project_id: uuid.UUID) -> LibraryRow:
        library = self._session.get(LibraryRow, library_id)
        if not library or library.project_id != project_id:
            raise DocumentServiceError("not_found", "Library not found", 404)
        return library

    def _document_count(self, library_id: uuid.UUID) -> int:
        return int(
            self._session.execute(
                select(func.count()).select_from(DocumentRow).where(DocumentRow.library_id == library_id)
            ).scalar_one()
        )

    def list_documents(self, library_id: uuid.UUID) -> list[DocumentResponse]:
        if not self._session.get(LibraryRow, library_id):
            raise DocumentServiceError("not_found", "Library not found", 404)
        rows = self._session.execute(
            select(DocumentRow).where(DocumentRow.library_id == library_id).order_by(DocumentRow.created_at.desc())
        ).scalars().all()
        return [DocumentResponse.from_row(row) for row in rows]

    def list_documents_paginated(
        self,
        library_id: uuid.UUID,
        *,
        page: int,
        page_size: int,
        search: str | None = None,
        status: str | None = None,
        sort: str = "updated_at",
        order: str = "desc",
    ) -> PaginatedResponse[DocumentResponse]:
        if not self._session.get(LibraryRow, library_id):
            raise DocumentServiceError("not_found", "Library not found", 404)
        page = clamp_page(page)
        page_size = clamp_page_size(page_size)
        filters = [DocumentRow.library_id == library_id]
        if search and search.strip():
            term = f"%{search.strip().casefold()}%"
            filters.append(
                func.lower(DocumentRow.original_filename).like(term) | func.lower(DocumentRow.filename).like(term)
            )
        if status and status.strip():
            filters.append(DocumentRow.status == status.strip().upper())

        total = int(
            self._session.execute(select(func.count()).select_from(DocumentRow).where(*filters)).scalar_one()
        )
        allowed_sort = {
            "original_filename": DocumentRow.original_filename,
            "mime_type": DocumentRow.mime_type,
            "size_bytes": DocumentRow.size_bytes,
            "chunk_count": DocumentRow.chunk_count,
            "status": DocumentRow.status,
            "created_at": DocumentRow.created_at,
            "updated_at": DocumentRow.updated_at,
        }
        sort_field = sort if sort in allowed_sort else "updated_at"
        sort_col = allowed_sort[sort_field]
        sort_order = order if order in {"asc", "desc"} else "desc"
        order_clause = (
            (sort_col.asc(), DocumentRow.id.asc())
            if sort_order == "asc"
            else (sort_col.desc(), DocumentRow.id.desc())
        )
        offset = (page - 1) * page_size
        rows = self._session.execute(
            select(DocumentRow)
            .where(*filters)
            .order_by(*order_clause)
            .offset(offset)
            .limit(page_size)
        ).scalars().all()
        pages = total_pages(total, page_size)
        if pages and page > pages:
            page = pages
        return PaginatedResponse(
            items=[DocumentResponse.from_row(row) for row in rows],
            page=page,
            page_size=page_size,
            total=total,
            total_pages=pages,
        )

    def rename_document(self, document_id: uuid.UUID, body: DocumentRename) -> DocumentResponse:
        row = self.get_document(document_id)
        label = body.original_filename.strip()
        if not label:
            raise DocumentServiceError("invalid_name", "Document name is required", 422)
        row.original_filename = label
        row.updated_at = datetime.now(timezone.utc)
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return DocumentResponse.from_row(row)

    def upload_document(
        self,
        *,
        library_id: uuid.UUID,
        filename: str,
        data: bytes,
    ) -> DocumentResponse:
        library = self._session.get(LibraryRow, library_id)
        if not library:
            raise DocumentServiceError("not_found", "Library not found", 404)

        limit = int(self._settings.knowledge_max_documents_per_library)
        if library.name != CHAT_ATTACHMENTS_LIBRARY_NAME and self._document_count(library_id) >= limit:
            raise DocumentServiceError(
                "LIBRARY_DOCUMENT_LIMIT_REACHED",
                f"This library has reached its {limit}-document limit.",
                409,
            )

        try:
            validated = validate_upload(
                filename=filename,
                data=data,
                max_bytes=self._max_bytes(),
                allowed_types=self._allowed_types(),
            )
            stored_name = sanitize_storage_filename(filename)
        except UploadValidationError as exc:
            raise DocumentServiceError(exc.code, exc.message, 400) from exc

        document_id = uuid.uuid4()
        key = storage_key(
            workspace_id=library.workspace_id,
            project_id=library.project_id,
            library_id=library.id,
            document_id=document_id,
            stored_filename=stored_name,
        )
        checksum = hashlib.sha256(data).hexdigest()
        now = datetime.now(timezone.utc)

        try:
            self._store.put(key, data)
        except ObjectStoreError as exc:
            raise DocumentServiceError("storage_failed", "Failed to store document", 500) from exc

        row = DocumentRow(
            id=document_id,
            workspace_id=library.workspace_id,
            project_id=library.project_id,
            library_id=library.id,
            filename=stored_name,
            original_filename=filename,
            mime_type=validated.mime_type,
            size_bytes=validated.size_bytes,
            storage_path=key,
            status="QUEUED",
            checksum=checksum,
            metadata_json={},
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        try:
            self._session.commit()
        except Exception:
            self._session.rollback()
            try:
                self._store.delete(key)
            except ObjectStoreError:
                logger.exception("orphan blob after failed metadata commit key=%s", key)
            raise

        self._session.refresh(row)
        return DocumentResponse.from_row(row)

    def delete_document(self, document_id: uuid.UUID) -> None:
        row = self.get_document(document_id)
        vector_store = build_vector_store(self._settings)
        if vector_store:
            try:
                vector_store.delete_document(document_id=document_id)
            except Exception as exc:
                raise DocumentServiceError(
                    "vector_delete_failed",
                    "Document was not deleted because vector cleanup failed",
                    500,
                ) from exc

        key = row.storage_path
        try:
            if self._store.exists(key):
                self._store.delete(key)
        except ObjectStoreError as exc:
            raise DocumentServiceError(
                "storage_delete_failed",
                "Document metadata was not removed because stored file could not be deleted",
                500,
            ) from exc

        self._session.delete(row)
        self._session.commit()

    def queue_reprocess(self, document_id: uuid.UUID) -> DocumentRow:
        row = self.get_document(document_id)
        meta = dict(row.metadata_json or {})
        meta["processing_stage"] = "queued"
        meta.pop("error_summary", None)
        row.status = "QUEUED"
        row.metadata_json = meta
        row.updated_at = datetime.now(timezone.utc)
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row
