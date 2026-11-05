"""Answer a question that names several metrics ("approval rate and delinquency rate by region").

Each metric is compiled and executed on its own from its governed formula, at the same breakdown, and the results
are merged here on the shared dimension values. The model never writes a join, so every number still comes from a
published definition. It works for any semantic model: metrics are found by their names and synonyms and
dimensions are matched by the order they appear in the question.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.casefold()).split())


def metric_aliases(registry: Any, metric_name: str) -> list[str]:
    config = registry.metrics[metric_name]
    context = config.get("ai_context") if isinstance(config.get("ai_context"), dict) else {}
    values = [metric_name, metric_name.replace("_", " "), context.get("display_name"), *(context.get("synonyms") or [])]
    out: list[str] = []
    for value in values:
        norm = _norm(str(value or ""))
        if len(norm) >= 4 and len(norm) <= 60 and norm not in out:
            out.append(norm)
    return out


def find_metrics(question: str, registry: Any) -> list[str]:
    """Metrics whose name or synonym appears in the question, in question order; [] when a phrase is ambiguous."""
    text = _norm(question)
    spans: list[tuple[int, int, str, str]] = []
    for metric in registry.metrics:
        for alias in metric_aliases(registry, metric):
            for match in re.finditer(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text):
                spans.append((match.start(), match.end(), metric, alias))
    spans.sort(key=lambda s: (-(s[1] - s[0]), s[0]))
    chosen: list[tuple[int, int, str]] = []
    for start, end, metric, alias in spans:
        overlapping = [c for c in chosen if start < c[1] and end > c[0]]
        if any(c[2] != metric and (c[1] - c[0]) == (end - start) and c[0] == start for c in overlapping):
            return []  # two metrics claim the same phrase
        if overlapping:
            continue
        chosen.append((start, end, metric))
    first: dict[str, int] = {}
    for start, _, metric in chosen:
        first[metric] = min(first.get(metric, start), start)
    return [m for m, _ in sorted(first.items(), key=lambda item: item[1])]


@dataclass
class DrillQuery:
    metric: str
    dataset: str
    dimensions: list[str]
    sql: str = ""
    resolution: dict[str, Any] = field(default_factory=dict)


def align_dimensions(question: str, metrics: list[str], registry: Any, definitions: dict[str, dict[str, Any]]) -> list[DrillQuery] | None:
    """One dimension list per metric, same length; None when a metric cannot be broken down the same way."""
    from app.ask_data.intent_satisfaction import infer_dimensions_from_question

    queries: list[DrillQuery] = []
    for metric in metrics:
        definition = definitions[metric]
        dataset = str(definition.get("base_dataset") or "")
        allowed = set(definition.get("allowed_dimensions") or [])
        dims = infer_dimensions_from_question(question, allowed, dataset_name=dataset, registry=registry)
        queries.append(DrillQuery(metric=metric, dataset=dataset, dimensions=list(dict.fromkeys(dims))))
    if len({len(q.dimensions) for q in queries}) != 1:
        return None
    return queries


def merge_results(results: list[dict[str, Any]], metrics: list[str]) -> dict[str, Any]:
    """Outer-join the per-metric results on their dimension values.

    The first metric keeps the `metric_value` column; the others are named after their metric.
    """
    if not results:
        return {"columns": [], "rows": [], "row_count": 0, "execution_ms": 0}
    dim_columns = [c for c in (results[0].get("columns") or []) if c != "metric_value"]
    rows_by_key: dict[tuple, dict[str, Any]] = {}
    for index, result in enumerate(results):
        own_dims = [c for c in (result.get("columns") or []) if c != "metric_value"]
        column = "metric_value" if index == 0 else metrics[index]
        for row in result.get("rows") or []:
            key = tuple(row.get(c) for c in own_dims)
            target = rows_by_key.setdefault(key, {name: value for name, value in zip(dim_columns, key)})
            target[column] = row.get("metric_value")
    columns = [*dim_columns, "metric_value", *metrics[1:]]
    rows = [{c: row.get(c) for c in columns} for row in rows_by_key.values()]
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "execution_ms": sum(float(r.get("execution_ms") or 0) for r in results),
    }


async def plan_queries(
    *,
    question: str,
    primary_metric: str,
    semantic_context: Any,
    qualified_sources: dict[str, str],
    executor: Any,
    state: dict[str, Any],
) -> tuple[list[DrillQuery], list[str]] | None:
    """Per-metric governed queries for a multi-metric question, or None to answer it the usual single-metric way."""
    from app.ask_data.value_filters import resolve_value_filters

    registry = semantic_context.registry
    metrics = find_metrics(question, registry)
    if len(metrics) < 2 or primary_metric not in metrics:
        return None
    # The resolved metric goes first so its SQL, chart and validation stay the primary ones.
    metrics = [primary_metric, *[m for m in metrics if m != primary_metric]]
    definitions = {m: semantic_context.metric_definition(m) for m in metrics}
    queries = align_dimensions(question, metrics, registry, definitions)
    if queries is None or any(q.dataset not in qualified_sources for q in queries):
        return None
    notes: list[str] = []
    for query in queries:
        definition = definitions[query.metric]
        filters = await resolve_value_filters(
            question=question,
            dataset_name=query.dataset,
            metric_expression=str(definition.get("expression") or ""),
            allowed_dimensions=set(definition.get("allowed_dimensions") or []),
            from_source=qualified_sources[query.dataset],
            semantic_context=semantic_context,
            executor=executor,
            state=state,
        )
        predicates = [f.predicate() for f in filters]
        query.sql = semantic_context.compile_governed(
            query.metric,
            question,
            query.dimensions,
            extra_predicates=predicates or None,
            from_source=qualified_sources[query.dataset],
        )
        query.resolution = {
            "status": "resolved",
            "metric": query.metric,
            "definition": definition,
            "dimensions": query.dimensions,
            "dimension_mismatch": [],
        }
        for flt in filters:
            from app.ask_data.column_labels import column_labels

            note = flt.describe(column_labels([flt.dimension], semantic_context=semantic_context).get(flt.dimension))
            if note not in notes:
                notes.append(note)
    return queries, notes
