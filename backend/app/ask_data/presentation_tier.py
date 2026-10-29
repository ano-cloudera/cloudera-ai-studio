"""Ask Data presentation tier (1=simple chat, 2=chat + expand, 3=Analysis Workspace)."""

from __future__ import annotations

from typing import Any, Literal

from app.ask_data.presentation_tier_config import PresentationTierConfig
from app.core.models import AskDataResponse, ChartSpec

PresentationTier = Literal[1, 2, 3]

_VISUAL_CHART_TYPES = frozenset({"bar", "line", "area", "scatter", "pie"})
_DEFAULT_CONFIG = PresentationTierConfig()


def _has_visual_chart(chart: ChartSpec | None, row_count: int) -> bool:
    if chart is None or row_count < 2:  # a single data point is a KPI, not a chart
        return False
    if chart.type not in _VISUAL_CHART_TYPES:
        return False
    return bool(chart.x and chart.y)


def tier_from_inquiry_brief(
    brief: dict[str, Any] | None,
    *,
    config: PresentationTierConfig | None = None,
) -> PresentationTier | None:
    cfg = config or _DEFAULT_CONFIG
    if not brief:
        return None
    if cfg.force_tier3_on_pareto and brief.get("wants_pareto"):
        return 3
    if cfg.force_tier3_on_operational_analysis and brief.get("wants_operational_analysis"):
        return 3
    if str(brief.get("analysis_mode") or "") == "pareto_contribution":
        return 3
    if brief.get("wants_rank"):
        limit = brief.get("rank_limit")
        min_rank_tier: PresentationTier = cfg.rank_min_tier if cfg.rank_min_tier in (1, 2, 3) else 2  # type: ignore[assignment]
        if limit is None:
            return 3
        try:
            n = int(limit)
        except (TypeError, ValueError):
            return 3
        return 3 if n > cfg.rank_tier3_above_n else min_rank_tier
    return None


def tier_from_response(
    response: AskDataResponse,
    *,
    config: PresentationTierConfig | None = None,
) -> PresentationTier:
    cfg = config or _DEFAULT_CONFIG
    if not cfg.enabled:
        return 1

    if response.route == "rag" or response.strategy == "rag":
        return 1
    if response.status != "SUCCESS":
        return 1

    row_count = max(int(response.data.row_count or 0), len(response.data.rows or []))
    insights = response.answer.insights or []
    implications = response.answer.business_implications or []
    insight_count = len(insights)
    implication_count = len(implications)

    if cfg.force_tier3_on_visual_chart and _has_visual_chart(response.chart_spec, row_count):
        return 3
    if row_count >= cfg.tier3_min_rows:
        return 3
    if insight_count >= cfg.tier3_min_insights or implication_count >= cfg.tier3_min_implications:
        return 3

    chart = response.chart_spec
    if chart is not None and chart.type == "kpi":
        return 1

    if (
        row_count <= cfg.tier1_max_rows
        and len(response.data.columns or []) <= cfg.tier1_max_columns
        and insight_count == 0
        and implication_count == 0
    ):
        return 1

    if insight_count >= 1 or row_count > cfg.tier1_max_rows or implication_count >= 1:
        return 2

    sql = (response.governed_sql or "").strip()
    exec_ms = float(response.data.execution_ms or 0)
    if sql or exec_ms > 0:
        return 1

    return 2


def compute_presentation_tier(
    response: AskDataResponse,
    *,
    inquiry_brief: dict[str, Any] | None = None,
    config: PresentationTierConfig | None = None,
) -> PresentationTier:
    cfg = config or _DEFAULT_CONFIG
    if not cfg.enabled:
        return 1
    from_brief = tier_from_inquiry_brief(inquiry_brief, config=cfg)
    from_payload = tier_from_response(response, config=cfg)
    if from_brief is None:
        return from_payload
    return max(from_brief, from_payload)  # type: ignore[return-value]


def attach_presentation_tier(
    response: AskDataResponse,
    *,
    inquiry_brief: dict[str, Any] | None = None,
    config: PresentationTierConfig | None = None,
) -> AskDataResponse:
    tier = compute_presentation_tier(response, inquiry_brief=inquiry_brief, config=config)
    if response.presentation_tier == tier:
        return response
    return response.model_copy(update={"presentation_tier": tier})
