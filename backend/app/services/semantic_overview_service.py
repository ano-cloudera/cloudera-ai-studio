"""Business-level semantic model overview (Phase 2)."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.platform_models import (
    SemanticDimensionRow,
    SemanticEntityRow,
    SemanticMetricRow,
    SemanticModelRow,
    SemanticRelationshipRow,
    SemanticTermRow,
    SemanticValidationRunRow,
    SemanticVersionRow,
)


class SemanticOverviewService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def model_overview(
        self,
        *,
        model_id: uuid.UUID,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> dict:
        model = self._session.get(SemanticModelRow, model_id)
        if not model or model.workspace_id != workspace_id or model.project_id != project_id:
            raise ValueError("Model not found")

        draft = self._session.execute(
            select(SemanticVersionRow)
            .where(SemanticVersionRow.semantic_model_id == model_id, SemanticVersionRow.status == "DRAFT")
            .order_by(SemanticVersionRow.version_number.desc())
            .limit(1)
        ).scalar_one_or_none()
        active = None
        if model.active_version_id:
            active = self._session.get(SemanticVersionRow, model.active_version_id)

        display_version = draft or active
        counts = {"entities": 0, "metrics": 0, "dimensions": 0, "relationships": 0, "terms": 0}
        issue_count = 0
        readiness = "unknown"
        if display_version:
            vid = display_version.id
            counts["entities"] = self._count(SemanticEntityRow, vid)
            counts["metrics"] = self._count(SemanticMetricRow, vid)
            counts["dimensions"] = self._count(SemanticDimensionRow, vid)
            counts["relationships"] = self._count(SemanticRelationshipRow, vid)
            counts["terms"] = self._count(SemanticTermRow, vid)
            readiness = display_version.activation_readiness or "unknown"
            if display_version.last_validation_run_id:
                run = self._session.get(SemanticValidationRunRow, display_version.last_validation_run_id)
                if run and run.summary:
                    issue_count = int(run.summary.get("error_count") or 0)

        state = "Draft"
        if draft and active:
            state = "Draft"
        elif active and not draft:
            state = "Published"
        elif draft and not active:
            state = "Draft"
        if issue_count > 0:
            state = "Needs attention"

        return {
            "model": {
                "id": str(model.id),
                "name": model.name,
                "key": model.key,
                "updated_at": model.updated_at.isoformat() if model.updated_at else None,
            },
            "state": state,
            "readiness": readiness,
            "issue_count": issue_count,
            "published_version_number": active.version_number if active else None,
            "draft_version_number": draft.version_number if draft else None,
            "counts": counts,
            "ready_to_publish": bool(draft) and issue_count == 0,
        }

    def _count(self, table, version_id: uuid.UUID) -> int:
        return int(
            self._session.execute(
                select(func.count()).select_from(table).where(table.semantic_version_id == version_id)
            ).scalar_one()
        )
