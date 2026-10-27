from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.platform_models import SemanticEntityRow, SemanticModelRow, SemanticVersionRow


def runtime_semantic_version_id(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    bundle_semantic_version_id: uuid.UUID | None,
) -> uuid.UUID | None:
    """Use runtime deployment version when provided; never registry ACTIVE draft."""
    return bundle_semantic_version_id


def find_entity_for_dataset(
    session: Session,
    *,
    semantic_version_id: uuid.UUID,
    dataset_name: str,
) -> SemanticEntityRow | None:
    name = dataset_name.strip()
    if not name:
        return None
    return session.execute(
        select(SemanticEntityRow).where(
            SemanticEntityRow.semantic_version_id == semantic_version_id,
            or_(SemanticEntityRow.key == name, SemanticEntityRow.name == name),
        )
    ).scalar_one_or_none()


def assert_version_in_project(
    session: Session,
    *,
    semantic_version_id: uuid.UUID,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
) -> SemanticVersionRow:
    version = session.get(SemanticVersionRow, semantic_version_id)
    if not version:
        raise ValueError("Semantic version not found")
    model = session.get(SemanticModelRow, version.semantic_model_id)
    if not model or model.workspace_id != workspace_id or model.project_id != project_id:
        raise ValueError("Semantic version project mismatch")
    return version
