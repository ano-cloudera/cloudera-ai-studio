"""Context an analyst would put next to a number before explaining it, the way Genie answers.

* The data coverage: the first and last date the dataset holds. A question about a period outside it ("December
  2025" when the data starts in January 2026) is told so instead of answered with an empty result or a zero.
* The overall value: a breakdown ("late rate per region") is answered next to the same metric over the same filters
  and period without the breakdown, so the answer can say "about twice the overall 11.26%" instead of only listing rows.

Both come from governed queries built here (never from SQL the model writes) and both are optional: any failure
leaves the answer as it was.
"""
from __future__ import annotations

import inspect
import logging
import re
import time
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 600
_COVERAGE: dict[str, tuple[float, dict[str, str] | None]] = {}

_MONTHS_EN = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
_MONTHS_ID = ("Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember")


def _time_expression(dataset: str, registry: Any) -> str | None:
    from app.ask_data.intent_satisfaction import _time_dimension_keys

    keys = _time_dimension_keys(dataset, registry)
    if not keys:
        return None
    field = (registry.dataset_fields.get(dataset) or {}).get(keys[0])
    if not field:
        return None
    expr = registry.ansi_expression(field).replace(f"{dataset}.", "d.")
    if not re.match(r"^d\.", expr.strip(), flags=re.I):
        expr = f"d.{expr}"
    return expr


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


async def data_coverage(*, executor: Any, state: dict[str, Any], dataset: str, source: str, registry: Any) -> dict[str, str] | None:
    """{"first": "2026-01-01", "last": "2026-08-31"} for the dataset's date column, cached per source; None without one."""
    cached = _COVERAGE.get(source)
    if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]
    expr = _time_expression(dataset, registry)
    if not expr:
        return None
    sql = f"SELECT MIN({expr}) AS first_date, MAX({expr}) AS last_date FROM {source} d"
    coverage: dict[str, str] | None = None
    try:
        result = executor.execute(sql, {**state, "context_query": True})
        if inspect.isawaitable(result):
            result = await result
        rows = result.get("rows") or []
        first, last = (_as_date(rows[0].get("first_date")), _as_date(rows[0].get("last_date"))) if rows else (None, None)
        if first and last:
            coverage = {"first": first.isoformat(), "last": last.isoformat()}
    except Exception:  # noqa: BLE001 - coverage is a nicety; the answer never depends on it
        logger.warning("data_coverage_failed source=%s", source)
        return None
    _COVERAGE[source] = (time.monotonic(), coverage)
    return coverage


def known_coverage() -> dict[str, str] | None:
    """The widest coverage seen so far in this process (for the agent planner, which has no data source of its own)."""
    spans = [value for stamp, value in _COVERAGE.values() if value and time.monotonic() - stamp < CACHE_TTL_SECONDS]
    if not spans:
        return None
    return {"first": min(s["first"] for s in spans), "last": max(s["last"] for s in spans)}


def coverage_label(coverage: dict[str, str] | None, language: str = "en") -> str | None:
    if not coverage:
        return None
    first, last = _as_date(coverage.get("first")), _as_date(coverage.get("last"))
    if not first or not last:
        return None
    months = _MONTHS_ID if language == "id" else _MONTHS_EN
    joiner = "sampai" if language == "id" else "to"
    return f"{first.day} {months[first.month - 1]} {first.year} {joiner} {last.day} {months[last.month - 1]} {last.year}"


def period_outside_coverage(question: str, coverage: dict[str, str] | None, today: date | None = None) -> str | None:
    """The label of a period the question names that lies wholly outside the data, else None."""
    if not coverage:
        return None
    first, last = _as_date(coverage.get("first")), _as_date(coverage.get("last"))
    if not first or not last:
        return None
    from app.ask_data.comparisons import find_periods
    from app.ask_data.intent_satisfaction import parse_yearless_period

    periods = [period for _, _, period in find_periods(question or "", today)]
    assumed = parse_yearless_period(question or "")
    if assumed is not None:
        periods.append(assumed)
    for period in periods:
        # PeriodRange.end is exclusive.
        if period.end <= first or period.start > last:
            return period.label
    return None


_RECENT = re.compile(
    r"\b(today|this (?:week|month|year|quarter)|latest|recent(?:ly)?|last (?:week|month)|so far|hari ini|minggu ini|bulan ini|tahun ini|kuartal ini"
    r"|terakhir|terbaru|terkini|sekarang|saat ini|minggu lalu|bulan lalu|kemarin)\b",
    re.I,
)


def asks_about_time(question: str) -> bool:
    """A question that names a period or "this week", "latest": only then is the data range worth telling."""
    from app.ask_data.comparisons import find_periods
    from app.ask_data.intent_satisfaction import parse_yearless_period

    text = question or ""
    return bool(_RECENT.search(text) or find_periods(text) or parse_yearless_period(text))


def no_data_message(question: str, coverage: dict[str, str] | None, language: str) -> str | None:
    label = coverage_label(coverage, language)
    if not label:
        return None
    outside = period_outside_coverage(question, coverage)
    if language == "id":
        head = f"Periode {outside} berada di luar data yang tersedia." if outside else "Tidak ada data yang cocok untuk pertanyaan dan filter tersebut."
        return f"{head} Data yang tersedia mencakup {label}."
    head = f"{outside} is outside the data that is available." if outside else "No data matches this question and these filters."
    return f"{head} The data covers {label}."


def outside_caveat(question: str, coverage: dict[str, str] | None, language: str) -> str | None:
    outside = period_outside_coverage(question, coverage)
    label = coverage_label(coverage, language)
    if not outside or not label:
        return None
    if language == "id":
        return f"Periode {outside} berada di luar data yang tersedia ({label}), jadi angka ini belum tentu mencerminkan periode itu."
    return f"{outside} is outside the available data ({label}), so this figure may not describe that period."


async def overall_value(*, executor: Any, state: dict[str, Any], sql: str) -> float | None:
    """The single value of an already validated governed query without a breakdown."""
    try:
        result = executor.execute(sql, {**state, "context_query": True})
        if inspect.isawaitable(result):
            result = await result
        rows = result.get("rows") or []
        if len(rows) != 1:
            return None
        value = rows[0].get("metric_value")
        return None if value is None or isinstance(value, bool) else float(value)
    except Exception:  # noqa: BLE001 - the overall value is context, never the answer
        logger.warning("overall_value_failed")
        return None
