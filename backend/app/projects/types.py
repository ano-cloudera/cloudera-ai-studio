from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkspaceRecord:
    id: uuid.UUID
    slug: str
    name: str


@dataclass(frozen=True)
class ProjectRecord:
    id: uuid.UUID
    workspace_id: uuid.UUID
    slug: str
    name: str
    ossie_root_path: str
    status: str
    default_connector_id: uuid.UUID | None = None
