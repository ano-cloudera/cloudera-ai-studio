from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.chat.attachments.constants import CHAT_ATTACHMENTS_LIBRARY_NAME
from app.db.platform_models import DocumentRow, LibraryRow, ProjectRow
from app.documents.library_status import document_status_counts, library_lifecycle_status
from app.documents.pagination import PaginatedResponse, clamp_page, clamp_page_size, total_pages
from app.documents.schemas import LibraryCreate, LibraryListItem, LibraryRename, LibraryResponse, LibraryUpdate
from app.core.config import Settings


class LibraryServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


LibrarySortField = Literal["name", "updated_at", "created_at", "document_count"]
LibrarySortOrder = Literal["asc", "desc"]


class LibraryService:
    def __init__(self, session: Session, *, document_limit: int = 100) -> None:
        self._session = session
        self._document_limit = document_limit

    def _library_response(self, row: LibraryRow) -> LibraryResponse:
        return LibraryResponse(
            id=row.id,
            workspace_id=row.workspace_id,
            project_id=row.project_id,
            name=row.name,
            description=row.description,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _list_item(
        self,
        row: LibraryRow,
        *,
        document_count: int = 0,
        failed_count: int = 0,
        processing_count: int = 0,
    ) -> LibraryListItem:
        base = self._library_response(row)
        lifecycle = library_lifecycle_status(
            document_count=document_count,
            failed_count=failed_count,
            processing_count=processing_count,
        )
        return LibraryListItem(
            **base.model_dump(),
            document_count=document_count,
            library_status=lifecycle,
            document_limit=self._document_limit,
        )

    def get_library(self, library_id: uuid.UUID) -> LibraryRow:
        row = self._session.get(LibraryRow, library_id)
        if not row:
            raise LibraryServiceError("not_found", "Library not found", 404)
        return row

    def get_library_detail(self, library_id: uuid.UUID) -> LibraryListItem:
        row = self.get_library(library_id)
        counts = document_status_counts(self._session, [row.id]).get(row.id, {})
        return self._list_item(
            row,
            document_count=int(counts.get("document_count", 0)),
            failed_count=int(counts.get("failed_count", 0)),
            processing_count=int(counts.get("processing_count", 0)),
        )

    def create_library(self, *, workspace_id: uuid.UUID, project_id: uuid.UUID, body: LibraryCreate) -> LibraryResponse:
        project = self._session.get(ProjectRow, project_id)
        if not project or project.workspace_id != workspace_id:
            raise LibraryServiceError("project_not_found", "Project not found for workspace", 404)
        name = body.name.strip()
        if not name:
            raise LibraryServiceError("invalid_name", "Library name is required", 422)
        existing = self._session.execute(
            select(LibraryRow).where(LibraryRow.project_id == project_id, LibraryRow.name == name)
        ).scalar_one_or_none()
        if existing:
            raise LibraryServiceError("duplicate_name", "Library name already exists in this project", 409)
        now = datetime.now(timezone.utc)
        row = LibraryRow(
            workspace_id=workspace_id,
            project_id=project_id,
            name=name,
            description=(body.description or "").strip() or None,
            status="active",
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return self._library_response(row)

    def rename_library(self, library_id: uuid.UUID, body: LibraryRename) -> LibraryResponse:
        return self.update_library(library_id, LibraryUpdate(name=body.name))

    def update_library(self, library_id: uuid.UUID, body: LibraryUpdate) -> LibraryResponse:
        row = self.get_library(library_id)
        name = body.name.strip()
        if not name:
            raise LibraryServiceError("invalid_name", "Library name is required", 422)
        existing = self._session.execute(
            select(LibraryRow).where(
                LibraryRow.project_id == row.project_id,
                LibraryRow.name == name,
                LibraryRow.id != library_id,
            )
        ).scalar_one_or_none()
        if existing:
            raise LibraryServiceError("duplicate_name", "Library name already exists in this project", 409)
        row.name = name
        fields = body.model_dump(exclude_unset=True)
        if "description" in fields:
            raw = fields["description"]
            row.description = (raw or "").strip() or None if raw is not None else None
        row.updated_at = datetime.now(timezone.utc)
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return self._library_response(row)

    def list_libraries(
        self,
        *,
        workspace_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
    ) -> list[LibraryListItem]:
        stmt = select(LibraryRow).order_by(LibraryRow.updated_at.desc())
        if project_id:
            stmt = stmt.where(LibraryRow.project_id == project_id)
        if workspace_id:
            stmt = stmt.where(LibraryRow.workspace_id == workspace_id)
        rows = [
            row
            for row in self._session.execute(stmt).scalars().all()
            if row.name != CHAT_ATTACHMENTS_LIBRARY_NAME
        ]
        counts = document_status_counts(self._session, [row.id for row in rows])
        return [
            self._list_item(
                row,
                document_count=int(counts.get(row.id, {}).get("document_count", 0)),
                failed_count=int(counts.get(row.id, {}).get("failed_count", 0)),
                processing_count=int(counts.get(row.id, {}).get("processing_count", 0)),
            )
            for row in rows
        ]

    def list_libraries_paginated(
        self,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        page: int,
        page_size: int,
        search: str | None = None,
        sort: LibrarySortField = "updated_at",
        order: LibrarySortOrder = "desc",
    ) -> PaginatedResponse[LibraryListItem]:
        page = clamp_page(page)
        page_size = clamp_page_size(page_size)
        filters = [
            LibraryRow.workspace_id == workspace_id,
            LibraryRow.project_id == project_id,
            LibraryRow.name != CHAT_ATTACHMENTS_LIBRARY_NAME,
        ]
        if search and search.strip():
            term = f"%{search.strip().casefold()}%"
            filters.append(func.lower(LibraryRow.name).like(term))

        total = int(
            self._session.execute(select(func.count()).select_from(LibraryRow).where(*filters)).scalar_one()
        )

        doc_count_subq = (
            select(
                DocumentRow.library_id.label("library_id"),
                func.count(DocumentRow.id).label("document_count"),
            )
            .group_by(DocumentRow.library_id)
            .subquery()
        )

        stmt = select(LibraryRow).where(*filters).outerjoin(
            doc_count_subq, LibraryRow.id == doc_count_subq.c.library_id
        )
        sort_col = LibraryRow.updated_at
        if sort == "name":
            sort_col = LibraryRow.name
        elif sort == "created_at":
            sort_col = LibraryRow.created_at
        elif sort == "document_count":
            sort_col = func.coalesce(doc_count_subq.c.document_count, 0)
        if order == "asc":
            stmt = stmt.order_by(sort_col.asc(), LibraryRow.id.asc())
        else:
            stmt = stmt.order_by(sort_col.desc(), LibraryRow.id.desc())

        offset = (page - 1) * page_size
        rows = self._session.execute(stmt.offset(offset).limit(page_size)).scalars().all()
        counts = document_status_counts(self._session, [row.id for row in rows])
        items = [
            self._list_item(
                row,
                document_count=int(counts.get(row.id, {}).get("document_count", 0)),
                failed_count=int(counts.get(row.id, {}).get("failed_count", 0)),
                processing_count=int(counts.get(row.id, {}).get("processing_count", 0)),
            )
            for row in rows
        ]
        pages = total_pages(total, page_size)
        if pages and page > pages:
            page = pages
        return PaginatedResponse(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
            total_pages=pages,
        )

    def delete_library(self, library_id: uuid.UUID, *, settings: Settings) -> None:
        from app.services.document_service import DocumentService

        self.get_library(library_id)
        doc_ids = list(
            self._session.execute(select(DocumentRow.id).where(DocumentRow.library_id == library_id)).scalars().all()
        )
        doc_service = DocumentService(settings, self._session)
        for doc_id in doc_ids:
            doc_service.delete_document(doc_id)
        row = self.get_library(library_id)
        self._session.delete(row)
        self._session.commit()
