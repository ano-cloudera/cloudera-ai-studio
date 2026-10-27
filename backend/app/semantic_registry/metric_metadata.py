"""Metric metadata helpers (allowed dimensions for Ask Data breakdown)."""

from __future__ import annotations

from typing import Any


def allowed_dimension_keys_from_metadata(metadata: dict[str, Any] | None) -> list[str] | None:
    if not metadata:
        return None
    raw = metadata.get("allowed_dimension_keys")
    if not isinstance(raw, list):
        return None
    cleaned = [str(k).strip() for k in raw if str(k).strip()]
    return cleaned


def merge_metric_metadata(data: dict[str, Any]) -> dict[str, Any]:
    """Apply top-level allowed_dimension_keys into metadata before persist."""
    out = dict(data)
    if "allowed_dimension_keys" not in out:
        return out
    keys = out.pop("allowed_dimension_keys")
    meta = dict(out.get("metadata") or {})
    if keys is None:
        meta.pop("allowed_dimension_keys", None)
    else:
        meta["allowed_dimension_keys"] = [str(k).strip() for k in keys if str(k).strip()]
    out["metadata"] = meta
    return out


def related_entity_keys(metric_source_entity_key: str, relationships) -> set[str]:
    keys = {metric_source_entity_key}
    for rel in relationships:
        if rel.from_entity_key == metric_source_entity_key:
            keys.add(rel.to_entity_key)
        if rel.to_entity_key == metric_source_entity_key:
            keys.add(rel.from_entity_key)
    return keys


def resolve_allowed_dimension_keys_for_publish(
    *,
    metric_source_entity_key: str,
    metric_metadata: dict[str, Any] | None,
    entity_dimension_keys: list[str],
    dimensions,
    relationships,
) -> list[str]:
    """Publish-time allowed_dimensions for OSSIE tempo extension."""
    stored = allowed_dimension_keys_from_metadata(metric_metadata)
    if stored is None:
        return sorted(entity_dimension_keys)

    related = related_entity_keys(metric_source_entity_key, relationships)
    dim_by_key = {d.key: d for d in dimensions}
    valid: list[str] = []
    for key in stored:
        dim = dim_by_key.get(key)
        if dim is not None and dim.source_entity_key in related:
            valid.append(key)
    return sorted(valid) if valid else sorted(entity_dimension_keys)
