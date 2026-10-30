"""Deterministic inquiry snapshot for OSSIE governed path (judge / replan)."""

from __future__ import annotations

import re
from typing import Any

from app.ask_data.presentation_tier import tier_from_inquiry_brief
from app.services.analysis_enrichment import detect_analysis_mode


def build_inquiry_brief(
    question: str,
    *,
    semantic_resolution: dict[str, Any] | None = None,
    query_plan: dict[str, Any] | None = None,
    session_last_metric: str | None = None,
) -> dict[str, Any]:
    text = (question or "").strip()
    lower = text.lower()
    resolution = semantic_resolution or {}
    plan = query_plan or {}

    wants_pareto = "pareto" in lower or any(
        t in lower
        for t in (
            "kontribusi",
            "kumulatif",
            "cumulatif",
            "cumulative",
            "nilai kumulatif",
            "persen kontribusi",
        )
    )
    wants_rank = bool(
        wants_pareto
        or re.search(r"\b(top\s*\d+|top\s+\d+|tertinggi|terendah|terbesar|terkecil|ranking|peringkat)\b", lower)
        or str(plan.get("analysis_type") or "").lower() == "ranking"
    )
    rank_limit = None
    m = re.search(r"\btop\s*(\d+)\b", lower) or re.search(r"\b(\d+)\s+(?:dc|produk|sku|material|cabang)\b", lower)
    if m:
        try:
            rank_limit = int(m.group(1))
        except ValueError:
            rank_limit = None

    wants_operational_analysis = bool(
        re.search(
            r"\b(analis[a]?\w*|rekomendasi|saran|perbaik\w*|langkah|what can we do|how (can|should) we|actionable|improve)\b",
            lower,
        )
    )
    wants_dc_grain = bool(re.search(r"\b(dc|gudang|cabang|distribution center)\b", lower))
    dc_top_n = bool(wants_rank and wants_dc_grain and re.search(r"\b(top\s*\d+\s+dc|\d+\s+dc\b|dc\b.*\b(tertinggi|terbesar|terbanyak|penumpukan))", lower))
    wants_product_grain = bool(
        wants_rank
        and re.search(r"\b(produk|sku|material|plu)\b", lower)
        and not dc_top_n
        and not (wants_dc_grain and rank_limit and rank_limit <= 20)
    )

    expected_metric = None
    if resolution.get("status") == "resolved":
        expected_metric = str(resolution.get("metric") or "") or None
    elif plan.get("metrics"):
        expected_metric = str(plan["metrics"][0])


    analysis_mode = detect_analysis_mode(text, expected_metric)

    brief: dict[str, Any] = {
        "question": text,
        "expected_metric": expected_metric,
        "expected_strategy": "governed" if resolution.get("status") == "resolved" else plan.get("strategy"),
        "analysis_mode": analysis_mode,
        "wants_pareto": wants_pareto,
        "wants_rank": wants_rank,
        "rank_limit": rank_limit,
        "wants_operational_analysis": wants_operational_analysis,
        "wants_product_grain": wants_product_grain,
        "wants_dc_grain": wants_dc_grain,
        "resolver_status": resolution.get("status"),
    }
    min_tier = tier_from_inquiry_brief(brief)
    if min_tier is not None:
        brief["presentation_min_tier"] = min_tier
    return brief
