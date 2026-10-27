from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.platform_models import (
    SemanticDimensionRow,
    SemanticEntityRow,
    SemanticMetricRow,
    SemanticRelationshipRow,
    SemanticTermRow,
    SemanticVersionRow,
)
from app.semantic_registry.governance_types import BREAKING, NON_BREAKING, POTENTIALLY_BREAKING


def _rows(session: Session, model, version_id: uuid.UUID):
    return list(session.execute(select(model).where(model.semantic_version_id == version_id)).scalars())


def _index(rows, fields: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in rows:
        payload = {f: getattr(row, f if f != "metadata" else "metadata_") for f in fields}
        out[row.key] = payload
    return out


def _classify(object_type: str, field: str, change: str) -> str:
    if change == "removed":
        if object_type in {"metric", "dimension", "entity", "relationship"}:
            return BREAKING
        return POTENTIALLY_BREAKING
    if change == "added":
        return NON_BREAKING
    if field in {"expression", "join_expression", "source_entity_key", "table_name", "schema", "source_column"}:
        return POTENTIALLY_BREAKING
    if field in {"synonyms", "description", "business_definition", "definition", "term"}:
        return NON_BREAKING
    return POTENTIALLY_BREAKING


class SemanticDiffService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def diff_versions(self, left_id: uuid.UUID, right_id: uuid.UUID) -> dict:
        left = self._session.get(SemanticVersionRow, left_id)
        right = self._session.get(SemanticVersionRow, right_id)
        if not left or not right:
            raise ValueError("Version not found")
        sections = []
        breaking: list[dict] = []
        for label, model, fields in (
            ("entities", SemanticEntityRow, ["name", "source_type", "schema", "table_name", "primary_key"]),
            ("metrics", SemanticMetricRow, ["name", "expression", "aggregation", "source_entity_key", "business_definition"]),
            ("dimensions", SemanticDimensionRow, ["name", "source_entity_key", "source_column", "data_type"]),
            ("relationships", SemanticRelationshipRow, ["from_entity_key", "to_entity_key", "join_expression", "join_type"]),
            ("glossary", SemanticTermRow, ["term", "definition", "related_metric_keys"]),
        ):
            left_map = _index(_rows(self._session, model, left_id), fields)
            right_map = _index(_rows(self._session, model, right_id), fields)
            added = [k for k in left_map if k not in right_map]
            removed = [k for k in right_map if k not in left_map]
            changed = []
            for key in left_map:
                if key not in right_map:
                    continue
                for field in fields:
                    if left_map[key].get(field) != right_map[key].get(field):
                        cls = _classify(label.rstrip("s"), field, "changed")
                        entry = {"key": key, "field": field, "from": right_map[key].get(field), "to": left_map[key].get(field), "classification": cls}
                        changed.append(entry)
                        if cls == BREAKING:
                            breaking.append({"section": label, **entry})
            for key in removed:
                breaking.append({"section": label, "key": key, "change": "removed", "classification": BREAKING})
            sections.append({"section": label, "added": added, "removed": removed, "changed": changed})
        return {
            "left_version_id": str(left_id),
            "right_version_id": str(right_id),
            "left_version_number": left.version_number,
            "right_version_number": right.version_number,
            "sections": sections,
            "breaking_changes": breaking,
        }
