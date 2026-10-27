"""Repair LLM chart specs against governed query columns (deterministic)."""
from __future__ import annotations

from typing import Any

from app.core.models import ChartSpec

_TIME_DIM_HINTS = (
    "date",
    "month",
    "calmonth",
    "period",
    "timestamp",
    "bulan",
    "transaction_date",
    "join_date",
)


def _is_numeric_cell(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    try:
        float(str(value).replace(",", ""))
        return True
    except (TypeError, ValueError):
        return False


def _looks_like_time_column(name: str) -> bool:
    lowered = name.casefold()
    return any(hint in lowered for hint in _TIME_DIM_HINTS)


def repair_chart_spec(
    chart: ChartSpec | None,
    *,
    columns: list[str] | set[str],
    rows: list[dict[str, Any]],
) -> ChartSpec | None:
    if not rows:
        return chart
    col_list = list(columns) if isinstance(columns, set) else list(columns or [])
    if not col_list:
        return chart

    dim_cols = [c for c in col_list if c != "metric_value"]
    sample = rows[0] if isinstance(rows[0], dict) else {}

    x = chart.x if chart else None
    y = chart.y if chart else None
    chart_type = chart.type if chart else None
    title = chart.title if chart else None

    if "metric_value" in col_list:
        if not y or y not in col_list or not _is_numeric_cell(sample.get(y)):
            y = "metric_value"
    if not x or x not in col_list:
        if len(dim_cols) == 1:
            x = dim_cols[0]
        elif dim_cols:
            x = dim_cols[0]

    if not x or not y:
        return None

    if chart_type not in ("bar", "line", "area", "scatter", "pie", "table", "kpi"):
        chart_type = "line" if _looks_like_time_column(x) else "bar"
    elif _looks_like_time_column(x) and chart_type == "bar" and len(rows) >= 3:
        chart_type = "line"

    if chart is None:
        return ChartSpec(type=chart_type, title=title or "Chart", x=x, y=y, series=chart.series if chart else None)

    updates: dict[str, Any] = {}
    if chart.x != x:
        updates["x"] = x
    if chart.y != y:
        updates["y"] = y
    if chart.type != chart_type:
        updates["type"] = chart_type
    if updates:
        return chart.model_copy(update=updates)
    return chart


def infer_chart_spec_from_result(
    *,
    columns: list[str],
    rows: list[dict[str, Any]],
    title: str | None = None,
    question: str = "",
) -> ChartSpec | None:
    if not rows or "metric_value" not in columns:
        return None
    dim_cols = [c for c in columns if c != "metric_value"]
    if not dim_cols:
        return ChartSpec(type="kpi", title=title or "Value", x=None, y="metric_value")
    x = dim_cols[0]
    lowered = question.casefold()
    for col in dim_cols:
        if _looks_like_time_column(col) or any(t in lowered for t in ("trend", "per bulan", "bulanan")):
            x = col
            break
    chart_type = "line" if _looks_like_time_column(x) or "trend" in lowered else "bar"
    return ChartSpec(type=chart_type, title=title or "Chart", x=x, y="metric_value")
