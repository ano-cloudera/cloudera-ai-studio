from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

DOCUMENT_STATUSES = frozenset({"UPLOADED", "QUEUED", "PROCESSING", "READY", "FAILED"})


@dataclass(frozen=True)
class LibraryRecord:
    id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class DocumentRecord:
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
