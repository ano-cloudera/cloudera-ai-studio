"""Governed compile hints for rank / judge replan (Phase C2)."""

from __future__ import annotations

from typing import Any


def rank_dimensions_for_brief(brief: dict[str, Any], allowed_dimensions: set[str]) -> list[str] | None:
    if not brief.get("wants_rank"):
        return None
    if brief.get("wants_dc_grain") and "dcname" in allowed_dimensions:
        return ["dcname"]
    if brief.get("wants_product_grain"):
        for name in ("material", "plu", "material_code"):
            if name in allowed_dimensions:
                return [name]
    return None
