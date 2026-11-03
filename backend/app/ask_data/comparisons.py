"""Comparisons that need the same governed metric computed more than once.

* Two periods ("compare the late rate of March to May with June to August 2026"): one query per period at the same
  breakdown, merged into the earlier value, the later value and the change.
* The overall value as a benchmark ("which regions are above the overall late rate", "more than 15 points below the
  overall rate"): one query at the breakdown and one without it, merged into the difference, then filtered.

Every number still comes from the metric's published formula; the model never writes SQL for either case, and the
results are combined here. It works for any semantic model: the metric is the one already resolved, the breakdown
comes from the words of the question, and the date column is the dataset's time dimension.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.ask_data.intent_satisfaction import (
    _MONTH_WORDS,
    _QUARTER_PATTERNS,
    _RANGE_PATTERN,
    _SINGLE_MONTH_PATTERN,
    PeriodRange,
    _month_start,
    infer_dimensions_from_question,
    period_sql_predicate,
)

_COMPARE = re.compile(
    r"\b(compare|compared|comparison|versus|vs|dibandingkan|dibanding|bandingkan|perbandingan|selisih|difference\s+between)\b",
    re.I,
)
_YEAR = re.compile(r"\b(20\d{2})\b")
_YEARLESS_QUARTER = re.compile(r"\bq([1-4])\b", re.I)


# ---- two periods ---------------------------------------------------------------------------------------------


def _recent_year(last_month: int, today: date) -> str:
    """The year of the most recent occurrence of a period that ends in `last_month` and has already finished."""
    year = today.year
    return str(year if _month_start(year, last_month + 1) <= today else year - 1)


def _range_period(match: re.Match[str], fallback_year: str | None) -> PeriodRange | None:
    m1, m2 = _MONTH_WORDS[match.group("m1").casefold()], _MONTH_WORDS[match.group("m2").casefold()]
    year = match.group("y2") or match.group("y1") or fallback_year
    if not year:
        return None
    first_year = match.group("y1") or year
    start, end = _month_start(int(first_year), m1), _month_start(int(year), m2 + 1)
    if start >= end:
        return None
    return PeriodRange(start, end, f"{start:%Y-%m} to {_month_start(int(year), m2):%Y-%m}")


def _quarter_period(quarter: int, year: int) -> PeriodRange:
    start = _month_start(year, (quarter - 1) * 3 + 1)
    return PeriodRange(start, _month_start(year, (quarter - 1) * 3 + 4), f"Q{quarter} {year}")


def find_periods(question: str, today: date | None = None) -> list[tuple[int, int, PeriodRange]]:
    """Every period named in the question, in order, with its text span. A year written once serves the others;
    a period without any year means its most recent finished occurrence."""
    today = today or date.today()
    text = question or ""
    years = _YEAR.findall(text)
    fallback = years[0] if years else None
    if not fallback:  # one year for every period of the question: the latest one in which all of them are over
        ends = [_MONTH_WORDS[m.group("m2").casefold()] for m in _RANGE_PATTERN.finditer(text)]
        ends += [int(m.group(1)) * 3 for m in _YEARLESS_QUARTER.finditer(text)]
        fallback = _recent_year(max(ends), today) if ends else None
    found: list[tuple[int, int, PeriodRange]] = []

    def add(start: int, end: int, period: PeriodRange | None) -> None:
        if period and not any(start < e and end > s for s, e, _ in found):
            found.append((start, end, period))

    for match in _RANGE_PATTERN.finditer(text):
        add(match.start(), match.end(), _range_period(match, fallback))
    for index, pattern in enumerate(_QUARTER_PATTERNS):
        for match in pattern.finditer(text):
            first, second = match.group(1), match.group(2)
            quarter, year = (int(first), int(second)) if index != 1 else (int(second), int(first))
            add(match.start(), match.end(), _quarter_period(quarter, year))
    if fallback:
        for match in _YEARLESS_QUARTER.finditer(text):
            add(match.start(), match.end(), _quarter_period(int(match.group(1)), int(fallback)))
    for match in _SINGLE_MONTH_PATTERN.finditer(text):
        month, year = _MONTH_WORDS[match.group("m").casefold()], int(match.group("y"))
        add(match.start(), match.end(), PeriodRange(_month_start(year, month), _month_start(year, month + 1), f"{year:04d}-{month:02d}"))
    return sorted(found, key=lambda item: item[0])


@dataclass(frozen=True)
class PeriodComparison:
    earlier: PeriodRange
    later: PeriodRange
    question_without_periods: str


def detect_period_comparison(question: str, today: date | None = None) -> PeriodComparison | None:
    """Exactly two different periods plus a comparison word; None for anything else."""
    if not _COMPARE.search(question or ""):
        return None
    spans = find_periods(question, today)
    if len(spans) != 2 or spans[0][2] == spans[1][2]:
        return None
    text = question
    for start, end, _ in reversed(spans):
        text = f"{text[:start]} {text[end:]}"
    earlier, later = sorted((spans[0][2], spans[1][2]), key=lambda period: period.start)
    return PeriodComparison(earlier, later, " ".join(text.split()))


# ---- the overall value as a benchmark -------------------------------------------------------------------------

_BENCHMARK = re.compile(
    r"\b(?P<direction>above|over|higher\s+than|exceed(?:s|ing)?|greater\s+than|di\s+atas|lebih\s+tinggi\s+dari|"
    r"below|under|lower\s+than|beneath|di\s+bawah|lebih\s+rendah\s+dari)\s+(?:the\s+)?"
    r"(?P<reference>overall|average|keseluruhan|rata[- ]rata|company|network|national|total)\b",
    re.I,
)
_VERSUS_OVERALL = re.compile(
    r"\b(?:compare[ds]?|comparison|versus|vs\.?|against|relative\s+to|dibandingkan(?:\s+dengan)?|dibanding|bandingkan)\b[^?.]{0,80}?"
    r"\b(?:overall|keseluruhan|(?:company|network|national|global)[- ](?:wide\s+)?(?:average|rate|value)|rata[- ]rata\s+(?:keseluruhan|perusahaan|nasional))\b",
    re.I,
)
_MARGIN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:%|percent(?:age)?[- ]points?|points?|pp|poin|persen)", re.I)
_WHICH = re.compile(r"\b(?:which|what|list|show|find|mana|apa)\s+(?P<phrase>[a-z_ ]+?)\s+(?:are|is|have|has|were|was|with|yang|perform|do)\b", re.I)


@dataclass(frozen=True)
class Benchmark:
    direction: str  # "above", "below", or "any" (compare with the overall value, no filtering)
    margin: float  # points (units of the metric) the group must be away from the overall value
    breakdown_text: str  # the question with a trailing "by <what it asked about>" for dimension inference


def detect_benchmark(question: str) -> Benchmark | None:
    match = _BENCHMARK.search(question or "")
    if not match:
        if _VERSUS_OVERALL.search(question or ""):
            return Benchmark("any", 0.0, question)  # every group, each with the overall value and its difference
        return None
    lowered = match.group("direction").casefold()
    direction = "below" if lowered.startswith(("below", "under", "lower", "beneath", "di bawah")) else "above"
    window = question[max(0, match.start() - 48) : match.start()]
    margin_match = _MARGIN.findall(window)
    margin = float(margin_match[-1].replace(",", ".")) if margin_match else 0.0
    which = _WHICH.search(question)
    breakdown_text = f"{question} by {which.group('phrase')}" if which else question
    return Benchmark(direction, margin, breakdown_text)


# ---- merging --------------------------------------------------------------------------------------------------


def _number(value: Any) -> float | None:
    try:
        return None if value is None or isinstance(value, bool) else float(value)
    except (TypeError, ValueError):
        return None


def merge_periods(results: list[dict[str, Any]]) -> dict[str, Any]:
    """results = [earlier, later]. Columns: the dimensions, metric_value (later), previous_value, change, change_pct."""
    earlier, later = results
    dims = [c for c in (later.get("columns") or []) if c != "metric_value"]
    rows_by_key: dict[tuple, dict[str, Any]] = {}
    for column, result in (("previous_value", earlier), ("metric_value", later)):
        for row in result.get("rows") or []:
            key = tuple(row.get(c) for c in dims)
            target = rows_by_key.setdefault(key, {name: value for name, value in zip(dims, key)})
            target[column] = row.get("metric_value")
    rows = []
    for row in rows_by_key.values():
        now, before = _number(row.get("metric_value")), _number(row.get("previous_value"))
        row["change"] = None if now is None or before is None else round(now - before, 4)
        row["change_pct"] = None if now is None or not before else round((now - before) * 100.0 / before, 2)
        rows.append(row)
    columns = [*dims, "metric_value", "previous_value", "change", "change_pct"]
    rows = [{c: row.get(c) for c in columns} for row in rows]
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "execution_ms": sum(float(r.get("execution_ms") or 0) for r in results),
    }


def merge_benchmark(results: list[dict[str, Any]], direction: str, margin: float) -> dict[str, Any]:
    """results = [grouped, overall]. Keeps the groups that are above (or below) the overall value by more than the margin."""
    grouped, overall = results
    overall_rows = overall.get("rows") or []
    overall_value = _number(overall_rows[0].get("metric_value")) if overall_rows else None
    dims = [c for c in (grouped.get("columns") or []) if c != "metric_value"]
    rows = []
    for row in grouped.get("rows") or []:
        value = _number(row.get("metric_value"))
        if value is None or overall_value is None:
            continue
        difference = round(value - overall_value, 4)
        if direction == "any" or (direction == "above" and difference > margin) or (direction == "below" and -difference > margin):
            rows.append({**{c: row.get(c) for c in dims}, "metric_value": row.get("metric_value"), "overall_value": overall_value, "difference": difference})
    rows.sort(key=lambda r: r["difference"], reverse=direction != "below")
    columns = [*dims, "metric_value", "overall_value", "difference"]
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "execution_ms": sum(float(r.get("execution_ms") or 0) for r in results),
    }


def merge_drill_results(drill: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    """Combine the executed queries of a drill-across state according to its kind."""
    kind = drill.get("kind")
    if kind == "periods":
        return merge_periods(results)
    if kind == "benchmark":
        meta = drill.get("meta") or {}
        return merge_benchmark(results, str(meta.get("direction")), float(meta.get("margin") or 0.0))
    from app.ask_data.drill_across import merge_results

    return merge_results(results, [q["metric"] for q in drill["queries"]])


# ---- planning -------------------------------------------------------------------------------------------------


async def plan_comparison(
    *,
    question: str,
    primary_metric: str,
    semantic_context: Any,
    qualified_sources: dict[str, str],
    executor: Any,
    state: dict[str, Any],
) -> tuple[dict[str, Any], list[str]] | None:
    """A drill-across state (queries, kind, meta) for a period or benchmark comparison, or None for a normal question."""
    from app.ask_data.value_filters import resolve_value_filters

    periods = detect_period_comparison(question)
    benchmark = None if periods else detect_benchmark(question)
    if not periods and not benchmark:
        return None
    registry = semantic_context.registry
    definition = semantic_context.metric_definition(primary_metric)
    dataset = str(definition.get("base_dataset") or "")
    source = qualified_sources.get(dataset)
    if not source:
        return None
    allowed = set(definition.get("allowed_dimensions") or [])
    dims_text = periods.question_without_periods if periods else benchmark.breakdown_text
    dimensions = list(dict.fromkeys(infer_dimensions_from_question(dims_text, allowed, dataset_name=dataset, registry=registry)))
    compare_with_overall = bool(benchmark and benchmark.direction == "any")
    if benchmark and not dimensions and not compare_with_overall:
        return None  # "above the overall rate" needs something to group by
    filters = await resolve_value_filters(
        question=question,
        dataset_name=dataset,
        metric_expression=str(definition.get("expression") or ""),
        allowed_dimensions=allowed,
        from_source=source,
        semantic_context=semantic_context,
        executor=executor,
        state=state,
    )
    value_predicates = [f.predicate() for f in filters]
    notes = [f.describe() for f in filters]
    if compare_with_overall and not dimensions and not value_predicates:
        return None  # nothing to compare: no breakdown and no named group

    def compile_query(sql_question: str, dims: list[str], predicates: list[str], filtered: bool = True) -> str:
        return semantic_context.compile_governed(
            primary_metric, sql_question, dims, extra_predicates=[*predicates, *(value_predicates if filtered else [])] or None, from_source=source
        )

    resolution = {"status": "resolved", "metric": primary_metric, "definition": definition, "dimensions": dimensions, "dimension_mismatch": []}
    queries: list[dict[str, Any]] = []
    if periods:
        for period in (periods.earlier, periods.later):
            predicate = period_sql_predicate(period, dataset_name=dataset, registry=registry)
            if not predicate:
                return None  # the dataset has no date column to compare on
            queries.append({"metric": primary_metric, "sql": compile_query(periods.question_without_periods, dimensions, [predicate]), "resolution": resolution, "dimensions": dimensions, "label": period.label})
        kind = "periods"
        meta = {"previous": periods.earlier.label, "current": periods.later.label}
    else:
        queries.append({"metric": primary_metric, "sql": compile_query(benchmark.breakdown_text, dimensions, []), "resolution": resolution, "dimensions": dimensions, "label": "by group"})
        # Comparing with the overall value means the whole data set, not only the group that was named.
        queries.append({"metric": primary_metric, "sql": compile_query(benchmark.breakdown_text, [], [], filtered=not compare_with_overall), "resolution": {**resolution, "dimensions": []}, "dimensions": [], "label": "overall"})
        kind = "benchmark"
        meta = {"direction": benchmark.direction, "margin": benchmark.margin}
    return {"kind": kind, "queries": queries, "columns": {}, "meta": meta}, notes
