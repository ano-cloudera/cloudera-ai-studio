"""Home: the figures the business watches most, read from the published semantic model, and a short briefing on them.

Nothing here is written for one data set. The KPIs are the model's headline metrics (metadata `headline`, 1 first; without any,
the first metrics); each is one governed query by month (ChatService.query_metric: compiled from the metric's own formula,
checked, no language-model call), which gives its overall value, its last complete month against the month before and a
sparkline. The main KPI is also shown by its most compact breakdown and, when one of its dimensions carries coordinates
(dimension metadata `geo`), on the map. The briefing is one model call over those figures, every figure in it checked.

Both are kept in memory for a while (per semantic version and code version), so opening Home is instant after the first time.
"""
from __future__ import annotations

import asyncio
import calendar
import json
import logging
from datetime import date
from pathlib import Path
from time import monotonic
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.ask_data.understanding import QueryIntent
from app.core.language import detect_language
from app.core.models import AskDataRequest, AskDataResponse

logger = logging.getLogger(__name__)

PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "home_briefing.md"
CACHE_SECONDS = 15 * 60
MAX_KPIS = 4
SPARK_MONTHS = 12
COMPACT_GROUPS = (3, 15)  # a breakdown worth charting on Home has this many groups
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_locks: dict[str, asyncio.Lock] = {}


class Briefing(BaseModel):
    model_config = ConfigDict(extra="ignore")
    headline: str
    points: list[str] = Field(default_factory=list)
    ask_next: list[str] = Field(default_factory=list)


def _cache_key(chat: Any, kind: str) -> str:
    from app.ask_data.answer_cache import code_version

    bundle = getattr(chat, "_runtime_bundle", None)
    version = str(getattr(bundle, "semantic_version_id", "") or getattr(bundle, "artifact_checksum", "") or "")
    return f"{kind}:{version}:{code_version()}"


def _cached(key: str) -> dict[str, Any] | None:
    hit = _cache.get(key)
    return hit[1] if hit and monotonic() - hit[0] < CACHE_SECONDS else None


def clear_cache() -> None:
    _cache.clear()


def _headline_metrics(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = list(catalog.get("metrics") or [])
    ranked = sorted((m for m in metrics if m.get("headline")), key=lambda m: int(m["headline"]))
    return (ranked or metrics)[:MAX_KPIS]


def _float(value: Any) -> float | None:
    try:
        return None if value is None or isinstance(value, bool) else float(value)
    except (TypeError, ValueError):
        return None


def _series(response: AskDataResponse) -> list[dict[str, Any]]:
    """[{month: 'YYYY-MM', value}] from a by-month result (the month is its first column)."""
    if not response.data.columns:
        return []
    month_column = response.data.columns[0]
    out = []
    for row in response.data.rows:
        value = _float(row.get("metric_value"))
        month = str(row.get(month_column) or "")[:7]
        if value is not None and len(month) == 7:
            out.append({"month": month, "value": value})
    return sorted(out, key=lambda item: item["month"])


def _complete_months(series: list[dict[str, Any]], coverage: dict[str, str] | None) -> list[dict[str, Any]]:
    """Without the last month when the data stops before its end (a month in progress is not compared with a full one)."""
    if not series or not coverage or not coverage.get("last"):
        return series
    try:
        last = date.fromisoformat(str(coverage["last"])[:10])
    except ValueError:
        return series
    month_end = calendar.monthrange(last.year, last.month)[1]
    if series[-1]["month"] == last.isoformat()[:7] and last.day < month_end:
        return series[:-1]
    return series


def _kpi(metric: dict[str, Any], response: AskDataResponse | None) -> dict[str, Any] | None:
    if response is None or response.status != "SUCCESS":
        return None
    data = response.data
    series = _complete_months(_series(response), data.data_coverage)
    value = _float(data.overall_value)
    if value is None and data.rows and len(data.rows) == 1:
        value = _float(data.rows[0].get("metric_value"))
    if value is None:
        return None
    kpi: dict[str, Any] = {
        "metric": metric["name"],
        "label": metric.get("label") or metric["name"],
        "description": metric.get("description") or "",
        "unit_format": data.unit_format,
        "value": value,
        "series": series[-SPARK_MONTHS:],
    }
    if len(series) >= 2:
        last, previous = series[-1], series[-2]
        kpi["last_month"] = last
        kpi["previous_month"] = previous
        kpi["change"] = round(last["value"] - previous["value"], 4)
        if previous["value"]:
            kpi["change_pct"] = round((last["value"] - previous["value"]) / abs(previous["value"]) * 100, 2)
    return kpi


def _compact_breakdown(metric: dict[str, Any], catalog: dict[str, Any]) -> str | None:
    """The first breakdown of the metric with a handful of groups (by the real values the model knows)."""
    entries = {e["key"]: e for e in (catalog.get("dimensions") or {}).get(metric.get("dataset") or "", [])}
    for key in metric.get("breakdowns") or []:
        values = (entries.get(key) or {}).get("values") or []
        if COMPACT_GROUPS[0] <= len(values) <= COMPACT_GROUPS[1] and not (entries.get(key) or {}).get("more_values"):
            return key
    return None


def _rows(response: AskDataResponse | None) -> dict[str, Any] | None:
    if response is None or response.status != "SUCCESS" or not response.data.rows:
        return None
    data = response.data
    return {
        "columns": list(data.columns),
        "rows": list(data.rows),
        "column_labels": dict(data.column_labels or {}),
        "overall_value": data.overall_value,
        "unit_format": data.unit_format,
        "geo_points": dict(data.geo_points or {}),
    }


async def build_home(chat: Any, request: AskDataRequest, *, refresh: bool = False) -> dict[str, Any]:
    """KPIs, the main KPI's trend, breakdown and map, from governed queries only."""
    catalog = await chat.agent_catalog(request)
    if not catalog or not catalog.get("metrics"):
        return {"status": "no_model", "kpis": []}
    key = _cache_key(chat, "home")
    if not refresh and (hit := _cached(key)):
        return hit
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:  # many viewers opening Home at once run the queries once
        if not refresh and (hit := _cached(key)):
            return hit
        payload = await _compute(chat, request, catalog)
        if payload.get("kpis"):
            _cache[key] = (monotonic(), payload)
        return payload


async def _compute(chat: Any, request: AskDataRequest, catalog: dict[str, Any]) -> dict[str, Any]:
    headline = _headline_metrics(catalog)
    language = "id" if detect_language(" ".join(str(m.get("label") or "") for m in headline)) == "id" else "en"

    async def ask(metric: str, label: str, **intent: Any) -> AskDataResponse | None:
        try:
            response, _frame, problems = await chat.query_metric(request, QueryIntent(metric=metric, language=language, **intent), label=label)
        except Exception:  # noqa: BLE001 - one tile failing leaves the others
            logger.exception("home_query_failed metric=%s", metric)
            return None
        if problems:
            logger.warning("home_query_invalid metric=%s problems=%s", metric, problems[:2])
        return response

    jobs: list[Any] = [
        ask(m["name"], m.get("label") or m["name"], by_month=bool(m.get("can_split_by_month"))) for m in headline
    ]
    main = headline[0]
    by = _compact_breakdown(main, catalog)
    geo_dimension = next((k for k in main.get("breakdowns") or [] if chat._geo_points([k])), None)
    jobs.append(ask(main["name"], main.get("label") or main["name"], breakdown=[by]) if by else asyncio.sleep(0, result=None))
    jobs.append(ask(main["name"], main.get("label") or main["name"], breakdown=[geo_dimension]) if geo_dimension else asyncio.sleep(0, result=None))
    results = await asyncio.gather(*jobs)
    kpis = [k for k in (_kpi(m, r) for m, r in zip(headline, results)) if k]
    first = results[0]
    coverage = first.data.data_coverage if first is not None and first.status == "SUCCESS" else None
    breakdown = _rows(results[len(headline)])
    place = _rows(results[len(headline) + 1])
    payload: dict[str, Any] = {
        "status": "ok" if kpis else "no_data",
        "language": language,
        "data_coverage": coverage,
        "kpis": kpis,
        "trend": kpis[0] if kpis and kpis[0].get("series") else None,
        "breakdown": {"metric": main["name"], "label": main.get("label"), "dimension": by, **breakdown} if breakdown else None,
        "map": {"metric": main["name"], "label": main.get("label"), "dimension": geo_dimension, **place} if place else None,
        "generated_at": date.today().isoformat(),
    }
    logger.info("home_built kpis=%s breakdown=%s map=%s", len(kpis), by, geo_dimension)
    return payload


def _briefing_figures(home: dict[str, Any]) -> tuple[list[dict[str, Any]], list[float]]:
    rows: list[dict[str, Any]] = []
    extras: list[float] = []
    for kpi in home.get("kpis") or []:
        extras += [v for v in (kpi.get("value"), kpi.get("change"), kpi.get("change_pct")) if isinstance(v, (int, float))]
        rows += [{"month": p["month"], "metric_value": p["value"]} for p in kpi.get("series") or []]
    for part in ("breakdown", "map"):
        block = home.get(part) or {}
        rows += list(block.get("rows") or [])
        if isinstance(block.get("overall_value"), (int, float)):
            extras.append(float(block["overall_value"]))
    from app.ask_data.answer_checks import computed_figures

    for part in ("breakdown", "map"):
        block = home.get(part) or {}
        computed = computed_figures(list(block.get("rows") or []), block.get("overall_value"))
        extras += [n for n in _numbers(computed)]
    return rows, extras


def _numbers(value: Any) -> list[float]:
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, dict):
        return [n for v in value.values() for n in _numbers(v)]
    if isinstance(value, list):
        return [n for v in value for n in _numbers(v)]
    return []


async def build_briefing(chat: Any, request: AskDataRequest, *, refresh: bool = False) -> dict[str, Any]:
    """Three or four points a director should know, from the Home figures; a point whose figures are not in them is left out."""
    home = await build_home(chat, request)
    if not home.get("kpis"):
        return {"status": "no_data"}
    key = _cache_key(chat, "briefing")
    if not refresh and (hit := _cached(key)):
        return hit
    from app.ask_data.answer_checks import computed_figures, unverified_figures

    language = home.get("language") or "en"
    facts: dict[str, Any] = {
        "language": language,
        "today": date.today().isoformat(),
        "data_coverage": home.get("data_coverage"),
        "kpis": [{k: v for k, v in kpi.items() if k != "description"} for kpi in home["kpis"]],
    }
    for part in ("breakdown", "map"):
        block = home.get(part)
        if block:
            facts[part] = {
                "metric": block.get("label"),
                "column_labels": block.get("column_labels"),
                "rows": block.get("rows")[:30],
                "overall_value": block.get("overall_value"),
                "computed": computed_figures(list(block.get("rows") or [])[:30], block.get("overall_value")),
            }
    _, provider = chat.provider_for(request)
    messages = [
        {"role": "system", "content": PROMPT.read_text(encoding="utf-8")},
        {"role": "user", "content": json.dumps(facts, ensure_ascii=False, default=str)},
    ]
    briefing = await provider.generate_structured(messages, Briefing, temperature=0.2, max_tokens=900)
    rows, extras = _briefing_figures(home)
    if unverified_figures([briefing.headline], rows, "", extras):
        logger.warning("home_briefing_headline_unverified")
        return {"status": "unverified"}
    points = [p for p in briefing.points if p.strip() and not unverified_figures([p], rows, "", extras)][:4]
    if len(points) < len(briefing.points):
        logger.info("home_briefing_points_dropped count=%s", len(briefing.points) - len(points))
    payload = {"status": "ok", "headline": briefing.headline.strip(), "points": points, "ask_next": [q for q in briefing.ask_next if q.strip()][:3], "language": language}
    _cache[key] = (monotonic(), payload)
    return payload
