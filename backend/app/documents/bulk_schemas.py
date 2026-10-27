from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, field_validator


class BulkDeleteLibrariesRequest(BaseModel):
    ids: list[str] = Field(min_length=1)

    @field_validator("ids")
    @classmethod
    def dedupe_ids(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in value:
            raw = (item or "").strip()
            if not raw or raw in seen:
                continue
            seen.add(raw)
            out.append(raw)
        if not out:
            raise ValueError("At least one library id is required")
        return out


class BulkDeleteDocumentsRequest(BaseModel):
    library_id: uuid.UUID | None = None
    ids: list[str] = Field(min_length=1)

    @field_validator("ids")
    @classmethod
    def dedupe_ids(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in value:
            raw = (item or "").strip()
            if not raw or raw in seen:
                continue
            seen.add(raw)
            out.append(raw)
        if not out:
            raise ValueError("At least one document id is required")
        return out


class BulkDeletedItem(BaseModel):
    id: str
    name: str


class BulkFailedItem(BaseModel):
    id: str
    name: str
    code: str
    message: str


class BulkDeleteResponse(BaseModel):
    requested: int
    deleted: list[BulkDeletedItem]
    failed: list[BulkFailedItem]
    deleted_count: int
    failed_count: int
