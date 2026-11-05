"""The "You could ask next" chips: every chip must be a question the assistant can answer when it is clicked.

The language model writes the suggestions; each one is kept only when it resolves to a governed metric of the active
model on its own (a chip is sent as a fresh question). What is dropped is replaced by suggestions built from the
model itself (the current metric by a breakdown it supports, or by month), so a chip never leads to "which metric do
you mean?".
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_MAX = 3


def _dimension_label(semantic_context: Any, dataset: str, key: str) -> str:
    field = (semantic_context.registry.dataset_fields.get(dataset) or {}).get(key) or {}
    ai = field.get("ai_context") if isinstance(field.get("ai_context"), dict) else {}
    label = str(ai.get("display_name") or field.get("label") or "").strip()
    if label:
        return label.casefold()
    short = key[len(dataset) + 1 :] if key.startswith(dataset + "_") else key
    words = short.replace("_", " ").split()
    if len(words) > 1 and words[-1] in {"name", "id", "code"}:
        words = words[:-1]
    return " ".join(words)


def answerable(question: str, semantic_context: Any) -> bool:
    try:
        return semantic_context.registry.resolve_metric(question).get("status") == "resolved"
    except Exception:
        return False


def built_suggestions(
    semantic_context: Any,
    *,
    metric: str | None,
    dimensions: list[str] | None,
    language: str,
) -> list[str]:
    """Suggestions made from the model: the metric by a breakdown it supports that was not used yet, and by month."""
    from app.ask_data.intent_satisfaction import pick_time_dimension
    from app.ask_data.metric_labels import humanize_metric_label

    out: list[str] = []
    try:
        names = [metric] if metric and metric in semantic_context.metrics else []
        names += [n for n in sorted(semantic_context.metrics) if n not in names]
    except Exception:
        return out
    indonesian = language == "id"
    for name in names:
        try:
            definition = semantic_context.metric_definition(name)
        except Exception:
            continue
        if definition.get("governance_status") == "reference":
            continue
        label = humanize_metric_label(name=name, definition=definition)
        dataset = str(definition.get("base_dataset") or "")
        allowed = [str(d) for d in definition.get("allowed_dimensions") or []]
        time_key = pick_time_dimension(dataset, set(allowed), semantic_context.registry) if dataset else None
        used = set(dimensions or []) if name == metric else set()
        dataset_def = semantic_context.datasets.get(dataset) or {}
        keys = {f"{dataset}_{k}" for k in dataset_def.get("primary_key") or []} | set(dataset_def.get("primary_key") or [])
        for key in allowed:
            if key in used or key == time_key or key in keys or key.endswith("_id") or key.endswith("_date"):
                continue
            field = (semantic_context.registry.dataset_fields.get(dataset) or {}).get(key) or {}
            if "dimension" not in field and field.get("datatype") not in (None, "String"):
                continue
            dim = _dimension_label(semantic_context, dataset, key)
            if not dim or dim.endswith(" id") or dim == "id":
                continue
            out.append(f"{label} per {dim}" if indonesian else f"{label} by {dim}")
            break
        if time_key and time_key not in used:
            out.append(f"{label} per bulan" if indonesian else f"{label} per month")
        if len(out) >= _MAX * 2:
            break
    return out


def settle_follow_ups(
    questions: list[str],
    *,
    semantic_context: Any,
    asked: str,
    metric: str | None,
    dimensions: list[str] | None,
    language: str,
) -> list[str]:
    seen = {" ".join(asked.casefold().split())}
    kept: list[str] = []
    dropped: list[str] = []
    for question in questions:
        key = " ".join(question.casefold().split())
        if not key or key in seen:
            continue
        if answerable(question, semantic_context):
            kept.append(question)
            seen.add(key)
        else:
            dropped.append(question)
    for question in built_suggestions(semantic_context, metric=metric, dimensions=dimensions, language=language):
        if len(kept) >= _MAX:
            break
        key = " ".join(question.casefold().split())
        if key not in seen and answerable(question, semantic_context):
            kept.append(question)
            seen.add(key)
    if dropped:
        logger.info("follow_up_suggestions_dropped count=%s examples=%r", len(dropped), dropped[:3])
    return kept[:_MAX]


def metric_labels(semantic_context: Any, limit: int = 40) -> dict[str, str]:
    from app.ask_data.conversation import metric_menu

    return {item["name"]: item["label"] for item in metric_menu(semantic_context, limit=limit)}
