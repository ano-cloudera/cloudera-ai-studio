"""Build tempo_governance.yaml for NFS deployments from registry metadata."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.platform_models import SemanticModelRow, SemanticTermRow, SemanticVersionRow
from app.semantic.runtime_extensions.config import (
    _profile_matches_datasets,
    list_profile_names,
    load_profile,
)


def _terms_to_phrase_map(terms: list[SemanticTermRow]) -> list[dict[str, Any]]:
    phrase_map: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in terms:
        dims = [str(d).strip() for d in (row.related_dimension_keys or []) if str(d).strip()]
        if not dims:
            continue
        phrases = [str(row.term).strip()]
        phrases.extend(str(s).strip() for s in (row.synonyms or []) if str(s).strip())
        phrases = list(dict.fromkeys(p for p in phrases if p))
        if not phrases:
            continue
        dim = dims[0]
        dedupe_key = f"{dim}::{phrases[0].casefold()}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        phrase_map.append({"phrases": phrases, "dimension": dim})
    return phrase_map


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


def _detect_profile_name(datasets: dict[str, Any]) -> str | None:
    for name in list_profile_names():
        profile = load_profile(name)
        if _profile_matches_datasets(profile.get("match"), datasets):
            return name
    return None


def build_runtime_extensions_block(
    datasets: dict[str, Any],
    terms: list[SemanticTermRow],
) -> dict[str, Any] | None:
    block: dict[str, Any] = {}
    profile = _detect_profile_name(datasets)
    if profile:
        block["profile"] = profile
    phrase_map = _terms_to_phrase_map(terms)
    if phrase_map:
        block["breakdown"] = {"phrase_map": phrase_map}
    return block or None


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
    runtime_extensions = build_runtime_extensions_block(datasets, terms)
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
    if runtime_extensions:
        governance["runtime_extensions"] = runtime_extensions
    return governance

