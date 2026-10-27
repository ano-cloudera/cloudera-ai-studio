"""Deterministic summaries when the analyst LLM fails on service-level governed rows."""

from __future__ import annotations

from typing import Any


def deterministic_service_unfulfilled_material_answer(
    question: str,
    metric: str | None,
    rows: list[dict[str, Any]],
) -> str | None:
    if not rows or not metric or "unfulfilled" not in metric.casefold():
        return None
    parts: list[str] = []
    office: str | None = None
    for index, row in enumerate(rows[:8]):
        if not isinstance(row, dict):
            continue
        material = row.get("material") or row.get("material_code")
        qty = row.get("metric_value")
        if material is None or qty is None:
            continue
        if office is None:
            office = row.get("sales_off") or row.get("sales_office")
        try:
            qty_f = float(qty)
        except (TypeError, ValueError):
            qty_f = qty
        parts.append(f"{index + 1}. {material}: unfulfilled qty {qty_f}")
    if not parts:
        return None
    header = "Material dengan unfulfilled quantity terbesar"
    if office:
        header += f" (sales office {office})"
    header += " — Q4 2024 (data governed):"
    return header + " " + "; ".join(parts) + "."
