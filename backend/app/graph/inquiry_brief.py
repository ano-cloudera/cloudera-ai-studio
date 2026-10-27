"""Deterministic inquiry snapshot for OSSIE governed path (judge / replan)."""

from __future__ import annotations

import re
from typing import Any

from app.core.config import get_settings
from app.semantic.domain_graph import build_business_context
from app.services.analysis_enrichment import detect_analysis_mode
from app.services.puppygraph_client import PuppyGraphClient


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

    business_context: dict[str, Any] | None = None
    settings = get_settings()
    if settings.business_graph_enabled:
        business_context = build_business_context(
            text,
            session_last_metric=session_last_metric,
        )
    puppygraph: dict[str, Any] | None = None
    client = PuppyGraphClient(settings)
    if client.configured:
        puppygraph = client.schema_summary()
    elif settings.puppygraph_enabled:
        puppygraph = {"enabled": False, "note": "PUPPYGRAPH_BASE_URL not set"}

    analysis_mode = detect_analysis_mode(text, expected_metric)

    return {
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
        "business_context": business_context,
        "puppygraph": puppygraph,
    }
