"""Turn dimension values named in a question ("Jawa Barat", "Digital") into governed WHERE predicates.

The values come from the data itself (a cached `SELECT DISTINCT` per low-cardinality text column), so nothing is
guessed: a word becomes a filter only when it is exactly one of the column's values. Columns used by the metric
formula, identifiers and high-cardinality columns are never filtered. The filters are reported back so the answer
can state its scope.
"""
from __future__ import annotations

import inspect
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

MAX_DISTINCT = 200
CACHE_TTL_SECONDS = 600.0
_TEXT_TYPES = {"string", "text", "varchar", "char"}
_CACHE: dict[tuple[str, str], tuple[float, list[str] | None]] = {}


@dataclass(frozen=True)
class ValueFilter:
    dimension: str
    expression: str
    values: tuple[str, ...]

    def predicate(self) -> str:
        quoted = ", ".join("'" + v.replace("'", "''") + "'" for v in self.values)
        if len(self.values) == 1:
            return f"{self.expression} = {quoted}"
        return f"{self.expression} IN ({quoted})"

    def describe(self) -> str:
        return f"{self.dimension} = {' or '.join(self.values)}"


def _normalize(text: str) -> str:
    return " ".join(text.casefold().replace("–", "-").split())


def match_values(question: str, catalog: dict[str, list[str]]) -> dict[str, list[str]]:
    """Dimension -> values of that dimension that the question names as whole words. Ambiguous values are dropped."""
    text = _normalize(question)
    found: dict[str, list[str]] = {}
    owners: dict[str, set[str]] = {}
    for dimension, values in catalog.items():
        for value in values:
            norm = _normalize(str(value))
            if len(norm) < 2 or norm.isdigit():
                continue
            if re.search(rf"(?<![a-z0-9]){re.escape(norm)}(?![a-z0-9])", text):
                found.setdefault(dimension, []).append(str(value))
                owners.setdefault(norm, set()).add(dimension)
    ambiguous = {norm for norm, dims in owners.items() if len(dims) > 1}
    cleaned: dict[str, list[str]] = {}
    for dimension, values in found.items():
        kept = [v for v in values if _normalize(v) not in ambiguous]
        # "Jawa" must not also match inside "Jawa Barat": keep only the longest value for overlapping names.
        kept = [v for v in kept if not any(v != o and _normalize(v) in _normalize(o) for o in kept)]
        if kept:
            cleaned[dimension] = kept
    return cleaned


def _candidate_dimensions(registry: Any, dataset_name: str, metric_expression: str, allowed: set[str]) -> list[str]:
    fields = registry.dataset_fields.get(dataset_name, {})
    primary = {str(k).casefold() for k in (registry.datasets.get(dataset_name, {}).get("primary_key") or [])}
    used = metric_expression.casefold()
    out = []
    for key in sorted(allowed):
        field = fields.get(key)
        if not field or str(field.get("datatype") or "").casefold() not in _TEXT_TYPES:
            continue
        if (field.get("dimension") or {}).get("is_time"):
            continue
        physical = registry.ansi_expression(field).strip()
        bare = re.sub(r"^d\.", "", physical, flags=re.IGNORECASE).casefold()
        if bare in primary or bare.endswith("_id") or not re.fullmatch(r"[a-z_][a-z0-9_]*", bare):
            continue
        if re.search(rf"\b{re.escape(bare)}\b", used):
            continue  # a column the metric formula already uses
        out.append(key)
    return out


async def _distinct_values(executor: Any, state: dict[str, Any], source: str, expression: str) -> list[str] | None:
    key = (source, expression)
    cached = _CACHE.get(key)
    if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]
    sql = f"SELECT DISTINCT {expression} AS v FROM {source} d WHERE {expression} IS NOT NULL LIMIT {MAX_DISTINCT + 1}"
    try:
        result = executor.execute(sql, state)
        if inspect.isawaitable(result):
            result = await result
        values = [str(row.get("v")) for row in (result.get("rows") or []) if isinstance(row, dict) and row.get("v") is not None]
    except Exception:  # noqa: BLE001 - a failed lookup must never break the question
        logger.warning("value_filter_lookup_failed column=%s", expression)
        return None
    cleaned: list[str] | None = None if len(values) > MAX_DISTINCT else values
    _CACHE[key] = (time.monotonic(), cleaned)
    return cleaned


async def resolve_value_filters(
    *,
    question: str,
    dataset_name: str,
    metric_expression: str,
    allowed_dimensions: set[str],
    from_source: str | None,
    semantic_context: Any,
    executor: Any,
    state: dict[str, Any],
) -> list[ValueFilter]:
    if not from_source:
        return []
    registry = semantic_context.registry
    catalog: dict[str, list[str]] = {}
    expressions: dict[str, str] = {}
    for key in _candidate_dimensions(registry, dataset_name, metric_expression, allowed_dimensions):
        expression = semantic_context._registry_dimension_expression(dataset_name, key, question)
        values = await _distinct_values(executor, state, from_source, expression)
        if values:
            catalog[key] = values
            expressions[key] = expression
    matches = match_values(question, catalog)
    return [ValueFilter(dimension=k, expression=expressions[k], values=tuple(v)) for k, v in matches.items()]


def clear_cache() -> None:
    _CACHE.clear()
