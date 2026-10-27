"""Read-only published semantic catalog for Ask Data browse panel."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.platform_models import SemanticDimensionRow, SemanticMetricRow, SemanticModelRow
from app.workspace.ask_data_settings import read_ask_data_settings


def _resolve_target_model(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    settings_json: dict | None,
) -> SemanticModelRow | None:
    settings = read_ask_data_settings(settings_json)
    pinned = (settings.default_semantic_model_id or "").strip()
    if pinned:
        try:
            model = session.get(SemanticModelRow, uuid.UUID(pinned))
        except ValueError:
            model = None
        if (
            model is not None
            and model.workspace_id == workspace_id
            and model.project_id == project_id
            and model.active_version_id
        ):
            return model
    rows = list(
        session.execute(
            select(SemanticModelRow).where(
                SemanticModelRow.workspace_id == workspace_id,
                SemanticModelRow.project_id == project_id,
                SemanticModelRow.active_version_id.isnot(None),
            )
        ).scalars()
    )
    if len(rows) == 1:
        return rows[0]
    return None


def build_semantic_catalog_payload(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    settings_json: dict | None,
) -> dict[str, Any]:
    model = _resolve_target_model(
        session,
        workspace_id=workspace_id,
        project_id=project_id,
        settings_json=settings_json,
    )
    if model is None or not model.active_version_id:
        return {"model": None, "metrics": [], "dimensions": []}
    version_id = model.active_version_id
    metrics = list(
        session.execute(
            select(SemanticMetricRow).where(SemanticMetricRow.semantic_version_id == version_id)
        ).scalars()
    )
    dimensions = list(
        session.execute(
            select(SemanticDimensionRow).where(SemanticDimensionRow.semantic_version_id == version_id)
        ).scalars()
    )
    return {
        "model": {
            "id": str(model.id),
            "name": model.name,
            "key": model.key,
        },
        "metrics": [
            {
                "id": str(m.id),
                "key": m.key,
                "name": m.name,
                "description": (m.description or "")[:300],
            }
            for m in sorted(metrics, key=lambda r: (r.name or r.key or "").casefold())
        ],
        "dimensions": [
            {
                "id": str(d.id),
                "key": d.key,
                "name": d.name,
                "description": (d.description or "")[:300],
            }
            for d in sorted(dimensions, key=lambda r: (r.name or r.key or "").casefold())
        ],
    }
