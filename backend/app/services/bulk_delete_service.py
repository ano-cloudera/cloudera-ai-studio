from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.documents.bulk_schemas import BulkDeleteResponse, BulkDeletedItem, BulkFailedItem
from app.services.document_service import DocumentService, DocumentServiceError
from app.services.library_service import LibraryService, LibraryServiceError


class BulkDeleteServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _parse_id(raw: str) -> uuid.UUID:
    return uuid.UUID(str(raw).strip())


class BulkDeleteService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._libraries = LibraryService(session, document_limit=settings.knowledge_max_documents_per_library)
        self._documents = DocumentService(settings, session)

    def delete_libraries(
        self,
        ids: list[str],
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> BulkDeleteResponse:
        deleted: list[BulkDeletedItem] = []
        failed: list[BulkFailedItem] = []
        for raw in ids:
            try:
                lib_id = _parse_id(raw)
            except ValueError:
                failed.append(
                    BulkFailedItem(id=raw, name=raw, code="invalid_id", message="Library id is not valid")
                )
                continue
            name = raw
            try:
                row = self._libraries.get_library(lib_id)
                name = row.name
                if row.workspace_id != workspace_id or row.project_id != project_id:
                    raise LibraryServiceError("forbidden", "Library is not accessible in this project", 403)
                self._libraries.delete_library(lib_id, settings=self._settings)
                deleted.append(BulkDeletedItem(id=str(lib_id), name=name))
            except LibraryServiceError as exc:
                failed.append(
                    BulkFailedItem(id=str(lib_id), name=name, code=exc.code, message=exc.message)
                )
            except Exception as exc:
                failed.append(
                    BulkFailedItem(
                        id=str(lib_id),
                        name=name,
                        code="LIBRARY_DELETE_FAILED",
                        message=str(exc) or "Library could not be deleted",
                    )
                )
        return BulkDeleteResponse(
            requested=len(ids),
            deleted=deleted,
            failed=failed,
            deleted_count=len(deleted),
            failed_count=len(failed),
        )

    def delete_documents(
        self,
        ids: list[str],
        *,
        project_id: uuid.UUID,
        library_id: uuid.UUID | None = None,
    ) -> BulkDeleteResponse:
        deleted: list[BulkDeletedItem] = []
        failed: list[BulkFailedItem] = []
        for raw in ids:
            try:
                doc_id = _parse_id(raw)
            except ValueError:
                failed.append(
                    BulkFailedItem(id=raw, name=raw, code="invalid_id", message="Document id is not valid")
                )
                continue
            name = raw
            try:
                row = self._documents.get_document(doc_id)
                name = row.original_filename
                if row.project_id != project_id:
                    raise DocumentServiceError("forbidden", "Document is not accessible in this project", 403)
                if library_id is not None and row.library_id != library_id:
                    raise DocumentServiceError(
                        "cross_library",
                        "Document does not belong to the specified library",
                        403,
                    )
                self._documents.delete_document(doc_id)
                deleted.append(BulkDeletedItem(id=str(doc_id), name=name))
            except DocumentServiceError as exc:
                failed.append(
                    BulkFailedItem(id=str(doc_id), name=name, code=exc.code, message=exc.message)
                )
            except Exception as exc:
                failed.append(
                    BulkFailedItem(
                        id=str(doc_id),
                        name=name,
                        code="DOCUMENT_DELETE_FAILED",
                        message=str(exc) or "Document could not be deleted",
                    )
                )
        return BulkDeleteResponse(
            requested=len(ids),
            deleted=deleted,
            failed=failed,
            deleted_count=len(deleted),
            failed_count=len(failed),
        )
