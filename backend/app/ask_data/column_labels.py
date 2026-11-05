"""Business names for the columns of a governed result: "delivery_shipments_region_name" is shown as "Region"."""
from __future__ import annotations

import re
from typing import Any

_DROP_LAST = {"name", "id", "code", "key"}


def _words(key: str, dataset: str) -> list[str]:
    short = key[len(dataset) + 1 :] if dataset and key.startswith(dataset + "_") else key
    words = [w for w in short.split("_") if w]
    if len(words) > 1 and words[-1] in _DROP_LAST:
        words = words[:-1]
    return words


def column_labels(columns: list[str], *, semantic_context: Any, sql: str = "", metric_label: str | None = None) -> dict[str, str]:
    """A label for every column that comes from the semantic model; other columns keep their own name."""
    labels: dict[str, str] = {}
    try:
        fields_by_dataset = semantic_context.registry.dataset_fields
    except Exception:
        return labels
    monthly = "date_trunc('month'" in (sql or "").casefold()
    for column in columns:
        if column == "metric_value":
            if metric_label:
                labels[column] = metric_label
            continue
        for dataset, fields in fields_by_dataset.items():
            field = fields.get(column)
            if not field:
                continue
            ai = field.get("ai_context") if isinstance(field.get("ai_context"), dict) else {}
            display = str(ai.get("display_name") or field.get("label") or "").strip()
            is_time = bool((field.get("dimension") or {}).get("is_time")) or str(field.get("datatype") or "").casefold() in {"date", "timestamp"}
            if monthly and (is_time or column.endswith("_date")):
                labels[column] = "Month"
            elif display:
                labels[column] = display
            else:
                labels[column] = " ".join(w.capitalize() for w in _words(column, dataset)) or column
            break
    return {k: re.sub(r"\s+", " ", v).strip() for k, v in labels.items()}
