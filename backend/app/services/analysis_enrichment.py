"""Deterministic post-query enrichment for governed analysis modes (no extra LLM)."""

from __future__ import annotations

import inspect
import re
from typing import Any, Callable, Awaitable

# Value metrics where contribution % vs company total is meaningful.
_PARETO_VALUE_METRICS = frozenset(
    {
        "material_sell_in_value",
        "material_sell_out_value",
        "material_sell_in_quantity",
        "material_sell_out_quantity",
        "sales_office_sell_in_value",
        "sales_office_material_sell_in_value",
        "b2b_branch_sell_out_value",
        "gross_billing_value",
    }
)

_CONTRIBUTION_TERMS = (
    "kontribusi",
    "persen kontribusi",
    "percent contribution",
    "kumulatif",
    "cumulatif",
    "cumulative",
    "nilai kumulatif",
    "pareto",
    "80/20",
    "80 20",
    "penggerak utama",
    "produk penggerak",
    "driving product",
)


def wants_contribution_analysis(question: str) -> bool:
    lowered = " ".join((question or "").casefold().split())
    return any(term in lowered for term in _CONTRIBUTION_TERMS)


def detect_analysis_mode(question: str, metric: str | None) -> str | None:
    if not metric or not wants_contribution_analysis(question):
        return None
    if metric in _PARETO_VALUE_METRICS or (
        "sell_in_value" in metric or "sell_out_value" in metric or metric.endswith("_value")
    ):
        if "ratio" in metric or "fill_rate" in metric:
            return None
        return "pareto_contribution"
    return None


def enrich_pareto_rows(rows: list[dict[str, Any]], company_total: float) -> tuple[list[dict[str, Any]], list[str]]:
    if not rows or company_total <= 0:
        return rows, _columns_from_rows(rows)
    base_columns = _columns_from_rows(rows)
    cumulative = 0.0
    enriched: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            value = float(row.get("metric_value") or 0)
        except (TypeError, ValueError):
            value = 0.0
        contribution = 100.0 * value / company_total
        cumulative += contribution
        enriched.append(
            {
                **row,
                "contribution_pct": round(contribution, 2),
                "cumulative_pct": round(cumulative, 2),
            }
        )
    columns = list(base_columns)
    for col in ("contribution_pct", "cumulative_pct"):
        if col not in columns:
            columns.append(col)
    return enriched, columns


def _columns_from_rows(rows: list[dict[str, Any]]) -> list[str]:
    if not rows or not isinstance(rows[0], dict):
        return []
    return list(rows[0].keys())


QueryExecutor = Callable[[str, str], dict[str, Any] | Awaitable[dict[str, Any]]]


async def apply_analysis_enrichment(
    *,
    question: str,
    resolution: dict[str, Any],
    result: dict[str, Any],
    semantic_context: Any,
    query_executor: QueryExecutor,
    request_id: str,
) -> dict[str, Any] | None:
    metric = str(resolution.get("metric") or "")
    mode = detect_analysis_mode(question, metric)
    if mode != "pareto_contribution":
        return None
    rows = result.get("rows") or []
    columns = list(result.get("columns") or [])
    if not rows or "metric_value" not in columns:
        return None

    extra_predicates = list(resolution.get("follow_up_entity_filters") or [])
    try:
        total_sql = semantic_context.compile_governed(
            metric,
            question,
            [],
            extra_predicates=extra_predicates or None,
            company_total_aggregate=True,
        )
    except (ValueError, KeyError):
        return None

    total_result = query_executor(total_sql, request_id)
    if inspect.isawaitable(total_result):
        total_result = await total_result
    total_rows = total_result.get("rows") or []
    if not total_rows:
        return None
    try:
        company_total = float(total_rows[0].get("metric_value") or 0)
    except (TypeError, ValueError):
        return None
    if company_total <= 0:
        return None

    enriched_rows, enriched_columns = enrich_pareto_rows(rows, company_total)
    caveat = (
        "Kontribusi % dan kumulatif % dihitung terhadap total governed untuk filter/periode yang sama "
        f"(bukan hanya jumlah {len(enriched_rows)} baris ranking)."
    )
    return {
        **result,
        "rows": enriched_rows,
        "columns": enriched_columns,
        "row_count": len(enriched_rows),
        "analysis_mode": mode,
        "analysis_enrichment": {
            "mode": mode,
            "company_total_metric_value": company_total,
            "caveat": caveat,
        },
    }
