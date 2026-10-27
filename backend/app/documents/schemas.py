from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LibraryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=4096)
    project_id: uuid.UUID | None = None


class LibraryResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class LibraryRename(BaseModel):
    name: str = Field(min_length=1, max_length=256)


class LibraryUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=4096)


class LibraryListItem(LibraryResponse):
    document_count: int = 0
    library_status: str = "ready"
    document_limit: int | None = None


class DocumentRename(BaseModel):
    original_filename: str = Field(min_length=1, max_length=512)


class DocumentResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    library_id: uuid.UUID
    filename: str
    original_filename: str
    mime_type: str
    size_bytes: int
    storage_path: str
    status: str
    checksum: str | None
    metadata: dict | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row) -> "DocumentResponse":
        return cls(
            id=row.id,
            workspace_id=row.workspace_id,
            project_id=row.project_id,
            library_id=row.library_id,
            filename=row.filename,
            original_filename=row.original_filename,
            mime_type=row.mime_type,
            size_bytes=row.size_bytes,
            storage_path=row.storage_path,
            status=row.status,
            checksum=row.checksum,
            metadata=row.metadata_json,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
