"""Backward-compatible shims; prefer `app.semantic.runtime_extensions` + governance profiles."""
from __future__ import annotations

from typing import Any

from app.semantic.runtime_extensions.config import load_profile
from app.semantic.runtime_extensions.engine import (
    apply_runtime_extensions,
    coerce_suggested_metric_metadata as _coerce_suggested_metric_metadata,
    display_name_for_metric as _display_name_for_metric,
    governed_join_state_patch as _governed_join_state_patch,
    infer_breakdown_dimensions as _infer_breakdown_dimensions,
    try_compile_governed_join_sql as _try_compile_governed_join_sql,
)
from app.semantic.runtime_extensions.config import resolve_runtime_extensions

_BANKING_PROFILE = load_profile("banking_demo")
METRIC_ENRICHMENT: dict[str, dict[str, Any]] = dict(_BANKING_PROFILE.get("metric_enrichment") or {})


def is_banking_demo_registry(datasets: dict[str, Any]) -> bool:
    return resolve_runtime_extensions(None, datasets) is not None


def _extensions_for_datasets(datasets: dict[str, Any]) -> dict[str, Any] | None:
    return resolve_runtime_extensions(None, datasets)


def infer_banking_breakdown_dimensions(question: str, allowed: set[str]) -> list[str]:
    ext = _BANKING_PROFILE
    return _infer_breakdown_dimensions(question, allowed, ext)


def infer_banking_segment_filter(question: str) -> str | None:
    joins = _BANKING_PROFILE.get("governed_joins") or []
    if not joins:
        return None
    from app.semantic.runtime_extensions.engine import _infer_dimension_filter

    return _infer_dimension_filter(question, joins[0])


def banking_governed_join_state_patch(
    datasets: dict[str, dict[str, Any]],
    sql: str,
    datasource_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    ext = _extensions_for_datasets(datasets)
    return _governed_join_state_patch(
        extensions=ext,
        datasets=datasets,
        sql=sql,
        datasource_context=datasource_context,
    )


def try_compile_banking_transactions_by_segment_sql(
    *,
    datasets: dict[str, dict[str, Any]],
    metric_expression: str,
    question: str,
    row_filter: str | None,
    period_predicate: str | None,
    extra_predicates: list[str] | None,
    sql_max_rows: int,
) -> str | None:
    ext = _extensions_for_datasets(datasets)
    return _try_compile_governed_join_sql(
        extensions=ext,
        datasets=datasets,
        metric_base_dataset="transactions",
        metric_expression=metric_expression,
        question=question,
        row_filter=row_filter,
        period_predicate=period_predicate,
        extra_predicates=extra_predicates,
        sql_max_rows=sql_max_rows,
    )


def display_name_for_metric(metric_key: str) -> str | None:
    return _display_name_for_metric(metric_key, _BANKING_PROFILE)


def apply_banking_demo_enrichment(
    *,
    datasets: dict[str, dict[str, Any]],
    metrics: dict[str, dict[str, Any]],
    dataset_fields: dict[str, dict[str, dict[str, Any]]],
) -> None:
    ext = _extensions_for_datasets(datasets)
    if ext:
        apply_runtime_extensions(
            ext,
            datasets=datasets,
            metrics=metrics,
            dataset_fields=dataset_fields,
        )


def coerce_suggested_metric_metadata(*, key: str, expression: str, name: str | None) -> tuple[str, str, str]:
    return _coerce_suggested_metric_metadata(
        key=key,
        expression=expression,
        name=name,
        extensions=_BANKING_PROFILE if key in METRIC_ENRICHMENT else None,
    )
