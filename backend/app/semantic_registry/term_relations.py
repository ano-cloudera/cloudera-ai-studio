"""Glossary term related-object key normalization and validation."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.platform_models import (
    SemanticDimensionRow,
    SemanticEntityRow,
    SemanticMetricRow,
)
from app.semantic_registry.registry_errors import SemanticRegistryError


def _dedupe_keys(keys: list[str] | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in keys or []:
        k = str(raw).strip()
        if not k:
            continue
        norm = k.casefold()
        if norm in seen:
            continue
        seen.add(norm)
        out.append(k)
    return out


def normalize_term_related_keys(
    *,
    related_metric_keys: list[str] | None,
    related_dimension_keys: list[str] | None,
    related_entity_keys: list[str] | None,
) -> tuple[list[str], list[str], list[str]]:
    return (
        _dedupe_keys(related_metric_keys),
        _dedupe_keys(related_dimension_keys),
        _dedupe_keys(related_entity_keys),
    )


def validate_term_related_keys(
    session: Session,
    version_id: uuid.UUID,
    *,
    related_metric_keys: list[str],
    related_dimension_keys: list[str],
    related_entity_keys: list[str],
) -> None:
    metric_keys = set(
        session.scalars(select(SemanticMetricRow.key).where(SemanticMetricRow.semantic_version_id == version_id)).all()
    )
    dimension_keys = set(
        session.scalars(
            select(SemanticDimensionRow.key).where(SemanticDimensionRow.semantic_version_id == version_id)
        ).all()
    )
    entity_keys = set(
        session.scalars(select(SemanticEntityRow.key).where(SemanticEntityRow.semantic_version_id == version_id)).all()
    )

    for mk in related_metric_keys:
        if mk not in metric_keys:
            raise SemanticRegistryError("invalid_reference", f"Metric `{mk}` was not found in this model version.", 400)
    for dk in related_dimension_keys:
        if dk not in dimension_keys:
            raise SemanticRegistryError(
                "invalid_reference", f"Dimension `{dk}` was not found in this model version.", 400
            )
    for ek in related_entity_keys:
        if ek not in entity_keys:
            raise SemanticRegistryError(
                "invalid_reference", f"Data model `{ek}` was not found in this model version.", 400
            )
