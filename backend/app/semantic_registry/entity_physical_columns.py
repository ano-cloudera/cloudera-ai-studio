"""Resolve physical table columns for semantic entities (measure validation)."""

from __future__ import annotations

import uuid
from typing import Any


def metadata_with_physical_columns(
    entity,
    *,
    session,
    version_id: uuid.UUID,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
) -> dict[str, Any]:
    """Return entity metadata, enriching with connector column list when missing."""
    meta = dict(getattr(entity, "metadata_", None) or {})
    if meta.get("physical_columns"):
        return meta
    connection_id = getattr(entity, "connection_id", None)
    table = getattr(entity, "table_name", None) or getattr(entity, "view_name", None)
    if not connection_id or not table:
        return meta
    from app.semantic_registry.entity_import import SemanticEntityImportService

    imp = SemanticEntityImportService(session)
    try:
        preview = imp.import_preview(
            version_id,
            workspace_id=workspace_id,
            project_id=project_id,
            connector_id=connection_id,
            catalog=getattr(entity, "catalog", None),
            schema=getattr(entity, "schema", None),
            table=table,
        )
    except Exception:
        return meta
    meta["physical_columns"] = [
        {
            "name": c.get("name"),
            "normalized_type": c.get("normalized_type"),
        }
        for c in preview.get("columns") or []
        if c.get("name")
    ]
    return meta
