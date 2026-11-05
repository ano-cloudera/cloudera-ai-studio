"""Build reference_governance.yaml for NFS deployments from registry metadata."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.platform_models import SemanticModelRow, SemanticTermRow, SemanticVersionRow


def _glossary_entries(terms: list[SemanticTermRow]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in terms:
        out.append(
            {
                "key": row.key,
                "term": row.term,
                "definition": row.definition,
                "synonyms": list(row.synonyms or []),
                "related_metric_keys": list(row.related_metric_keys or []),
                "related_dimension_keys": list(row.related_dimension_keys or []),
                "related_entity_keys": list(row.related_entity_keys or []),
            }
        )
    return out


def build_publish_governance(
    session: Session,
    *,
    version_id: uuid.UUID,
    model: SemanticModelRow,
    datasets: dict[str, Any],
) -> dict[str, Any]:
    version = session.get(SemanticVersionRow, version_id)
    terms = list(
        session.execute(
            select(SemanticTermRow)
            .where(SemanticTermRow.semantic_version_id == version_id)
            .order_by(SemanticTermRow.key)
        ).scalars()
    )
    governance: dict[str, Any] = {
        "ambiguities": [],
        "unknown_metric_question": "Which metric would you like to report on?",
        "scope": {
            "semantic_model_id": str(model.id),
            "semantic_model_key": model.key,
            "semantic_version_id": str(version_id),
            "semantic_version_number": version.version_number if version else None,
        },
        "glossary": _glossary_entries(terms),
    }
    return governance

