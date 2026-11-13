"""Home: the figures the business watches most, read from the published semantic model, and a short briefing on them.

Nothing here is written for one data set. The KPIs are the model's headline metrics (metadata `headline`, 1 first; without any,
the first metrics); each is one governed query by month (ChatService.query_metric: compiled from the metric's own formula,
checked, no language-model call), which gives its overall value, its last complete month against the month before and a
sparkline. The main KPI is also shown by its most compact breakdown and, when one of its dimensions carries coordinates
(dimension metadata `geo`), on the map. The briefing is one model call over those figures, every figure in it checked.

Both are kept on disk next to the answer cache (diskcache), per semantic version, so they survive a restart or a deploy. A
kept result is served at once; when it is older than FRESH_SECONDS it is also recomputed in the background for the next
viewer. warm() computes both ahead of the first viewer, at startup and after a model is published.
"""
from __future__ import annotations

import asyncio
import calendar
import json
import logging
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from time import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.ask_data.understanding import QueryIntent
from app.core.models import AskDataRequest, AskDataResponse

logger = logging.getLogger(__name__)

PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "home_briefing.md"
SCHEMA = 3  # raise when the payload's shape changes, so an older kept payload is not served
FRESH_SECONDS = 15 * 60
KEEP_SECONDS = 14 * 24 * 3600
MAX_KPIS = 4
SPARK_MONTHS = 12
COMPACT_GROUPS = (3, 15)  # a breakdown worth charting on Home has this many groups
MAX_CANDIDATES = 3  # breakdowns tried for the main KPI; the one where the groups differ most is shown

_memory: dict[str, dict[str, Any]] = {}
_store: Any = None
_store_lock = threading.Lock()
_locks: dict[str, asyncio.Lock] = {}
_refreshing: set[str] = set()
_tasks: set[asyncio.Task] = set()


class Briefing(BaseModel):
    model_config = ConfigDict(extra="ignore")
    headline: str
    what_happened: str = ""
    why_it_matters: str = ""
    look_next: list[str] = Field(default_factory=list)
    ask_next: list[str] = Field(default_factory=list)


# --- keeping ----------------------------------------------------------------------------------------------------------


def _disk(chat: Any) -> Any:
    """The diskcache store next to the answer cache, or None (then memory only)."""
    global _store
    if _store is not None:
        return None if _store is False else _store  # a Cache with no entries is falsy, so never test it with `or`
    with _store_lock:
        if _store is None:
            _store = False
            try:
                import diskcache

                from app.ask_data.answer_cache import cache_directory

                answers = cache_directory(getattr(chat, "settings", None))
                if answers is not None:
                    directory = Path(answers).parent / "home"
                    directory.mkdir(parents=True, exist_ok=True)
                    _store = diskcache.Cache(str(directory), size_limit=32 * 1024 * 1024)
            except Exception:  # noqa: BLE001 - memory still keeps it for this process
                logger.warning("home_cache_disk_unavailable")
                _store = False
    return None if _store is False else _store


def _key(chat: Any, kind: str, language: str = "en") -> str:
    bundle = getattr(chat, "_runtime_bundle", None)
    version = str(getattr(bundle, "semantic_version_id", "") or getattr(bundle, "artifact_checksum", "") or "")
    return f"{kind}:{SCHEMA}:{language}:{version}"


def _read(chat: Any, key: str) -> dict[str, Any] | None:
    store = _disk(chat)
    try:
        value = store.get(key) if store is not None else _memory.get(key)
    except Exception:  # noqa: BLE001
        value = _memory.get(key)
    return value if isinstance(value, dict) and isinstance(value.get("payload"), dict) else None


def _write(chat: Any, key: str, payload: dict[str, Any]) -> None:
    value = {"stored": time(), "payload": payload}
    _memory[key] = value
    store = _disk(chat)
    if store is not None:
        try:
            store.set(key, value, expire=KEEP_SECONDS)
        except Exception:  # noqa: BLE001
            logger.warning("home_cache_write_failed")


def _age(value: dict[str, Any]) -> float:
    return time() - float(value.get("stored") or 0)


def clear_cache() -> None:
    global _store
    _memory.clear()
    if _store is not None and _store is not False:
        try:
            _store.clear()
        except Exception:  # noqa: BLE001
            pass
    _store = None
    _refreshing.clear()


def _in_background(key: str, work: Any) -> None:
    """Recompute once for the next viewer; the current one already has the kept result."""
    if key in _refreshing:
        work.close()
        return
    _refreshing.add(key)

    async def run() -> None:
        try:
            await work
        except Exception:  # noqa: BLE001 - the kept result stays
            logger.exception("home_refresh_failed key=%s", key)
        finally:
            _refreshing.discard(key)

    task = asyncio.create_task(run())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


# --- the figures ------------------------------------------------------------------------------------------------------


def _headline_metrics(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    """The metrics the model's author marked "Show on Home", in their order. None marked: none shown (Home never picks
    metrics by itself, so what it shows is always what the model says matters)."""
    metrics = list(catalog.get("metrics") or [])
    return sorted((m for m in metrics if m.get("headline")), key=lambda m: int(m["headline"]))[:MAX_KPIS]


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


def _unit(chat: Any, metric: str) -> str | None:
    """The metric's unit as the model declares it (KL, %, IDR), shown beside its figures."""
    try:
        unit = chat.dependencies.semantic_context.metric_definition(metric).get("unit")
    except Exception:  # noqa: BLE001
        return None
    return str(unit).strip() or None if unit else None


def _kpi(metric: dict[str, Any], response: AskDataResponse | None, unit: str | None) -> dict[str, Any] | None:
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
        "unit": unit,
        "value": value,
        "series": series[-SPARK_MONTHS:],
        "better": metric.get("better"),  # "up", "down" or None, as the model's author declared it
        "target": metric.get("target"),
    }
    if len(series) >= 2:
        last, previous = series[-1], series[-2]
        kpi["last_month"] = last
        kpi["previous_month"] = previous
        kpi["change"] = round(last["value"] - previous["value"], 4)
        if previous["value"]:
            kpi["change_pct"] = round((last["value"] - previous["value"]) / abs(previous["value"]) * 100, 2)
    return kpi


def _compact_breakdowns(metric: dict[str, Any], catalog: dict[str, Any]) -> list[str]:
    """The breakdowns of the metric with a handful of groups (by the real values the model knows), at most MAX_CANDIDATES."""
    entries = {e["key"]: e for e in (catalog.get("dimensions") or {}).get(metric.get("dataset") or "", [])}
    found = []
    for key in metric.get("breakdowns") or []:
        values = (entries.get(key) or {}).get("values") or []
        if COMPACT_GROUPS[0] <= len(values) <= COMPACT_GROUPS[1] and not (entries.get(key) or {}).get("more_values"):
            found.append(key)
    return found[:MAX_CANDIDATES]


def _spread(response: AskDataResponse | None) -> float:
    """How much the groups of a breakdown differ, relative to the overall value: the breakdown worth showing is the one where
    something stands out. 0 when it cannot be told."""
    if response is None or response.status != "SUCCESS":
        return 0.0
    values = [v for v in (_float(row.get("metric_value")) for row in response.data.rows) if v is not None]
    if len(values) < COMPACT_GROUPS[0]:
        return 0.0
    scale = abs(_float(response.data.overall_value) or 0.0) or (sum(abs(v) for v in values) / len(values)) or 1.0
    return (max(values) - min(values)) / scale


def _rows(response: AskDataResponse | None, unit: str | None) -> dict[str, Any] | None:
    if response is None or response.status != "SUCCESS" or not response.data.rows:
        return None
    data = response.data
    return {
        "columns": list(data.columns),
        "rows": list(data.rows),
        "column_labels": dict(data.column_labels or {}),
        "overall_value": data.overall_value,
        "unit_format": data.unit_format,
        "unit": unit,
        "geo_points": dict(data.geo_points or {}),
    }


def _standout(block: dict[str, Any] | None, metric: dict[str, Any]) -> dict[str, Any] | None:
    """The groups (or places) furthest from the overall value of the main KPI, in the direction the model calls worse when it
    says which way is good, else either way; the most detailed block is used (places before groups)."""
    if not block or not isinstance(block.get("overall_value"), (int, float)):
        return None
    column = next((c for c in block.get("columns") or [] if c != "metric_value"), None)
    if not column:
        return None
    overall = float(block["overall_value"])
    better = metric.get("better")
    rows = []
    for row in block.get("rows") or []:
        value = _float(row.get("metric_value"))
        if value is None or row.get(column) in (None, ""):
            continue
        gap = value - overall
        worse = -gap if better == "up" else gap if better == "down" else abs(gap)
        rows.append({"group": str(row[column]), "value": value, "difference": round(gap, 4), "_worse": worse})
    rows = [r for r in sorted(rows, key=lambda r: r["_worse"], reverse=True) if r["_worse"] > 0][:3]
    if not rows:
        return None
    for r in rows:
        r.pop("_worse")
    return {
        "metric": metric["name"],
        "label": metric.get("label") or metric["name"],
        "by": (block.get("column_labels") or {}).get(column) or column,
        "overall_value": overall,
        "unit_format": block.get("unit_format"),
        "unit": block.get("unit"),
        "better": better,
        "groups": rows,
    }


async def build_home(chat: Any, request: AskDataRequest, *, refresh: bool = False, language: str = "en") -> dict[str, Any]:
    """KPIs, the main KPI's trend, breakdown and map, from governed queries only; a kept result is served at once.
    `language` is the language of the page and of the briefing; the labels come from the semantic model as its author wrote them."""
    chat._sync_runtime_for_request(request)  # the model Ask Data answers from, so the key names its version
    key = _key(chat, "home", language)
    kept = None if refresh else _read(chat, key)
    if kept is not None:
        if _age(kept) > FRESH_SECONDS:
            _in_background(key, _compute_and_keep(chat, request, key, language))
        return kept["payload"]
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:  # many viewers opening Home at once run the queries once
        kept = None if refresh else _read(chat, key)
        if kept is not None:
            return kept["payload"]
        return await _compute_and_keep(chat, request, key, language)


async def _compute_and_keep(chat: Any, request: AskDataRequest, key: str, language: str = "en") -> dict[str, Any]:
    catalog = await chat.agent_catalog(request)
    if not catalog or not catalog.get("metrics"):
        return {"status": "no_model", "kpis": []}
    if not _headline_metrics(catalog):
        return {"status": "no_home_metrics", "kpis": [], "language": language, "metric_count": len(catalog["metrics"])}
    payload = await _compute(chat, request, catalog, language)
    if payload.get("kpis"):
        _write(chat, key, payload)
    return payload


async def _compute(chat: Any, request: AskDataRequest, catalog: dict[str, Any], language: str = "en") -> dict[str, Any]:
    headline = _headline_metrics(catalog)

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
    candidates = _compact_breakdowns(main, catalog)
    geo_dimension = next((k for k in main.get("breakdowns") or [] if chat._geo_points([k])), None)
    jobs += [ask(main["name"], main.get("label") or main["name"], breakdown=[key]) for key in candidates]
    jobs.append(ask(main["name"], main.get("label") or main["name"], breakdown=[geo_dimension]) if geo_dimension else asyncio.sleep(0, result=None))
    results = list(await asyncio.gather(*jobs))
    place_response = results.pop()
    tried = results[len(headline):]
    best = max(range(len(tried)), key=lambda i: _spread(tried[i]), default=None)
    by = candidates[best] if best is not None and _spread(tried[best]) > 0 else None
    results = results[: len(headline)] + [tried[best] if by else None, place_response]
    units = {m["name"]: _unit(chat, m["name"]) for m in headline}
    kpis = [k for k in (_kpi(m, r, units[m["name"]]) for m, r in zip(headline, results)) if k]
    first = results[0]
    coverage = first.data.data_coverage if first is not None and first.status == "SUCCESS" else None
    breakdown = _rows(results[len(headline)], units[main["name"]])
    place = _rows(results[len(headline) + 1], units[main["name"]])
    payload: dict[str, Any] = {
        "status": "ok" if kpis else "no_data",
        "language": language,
        "data_coverage": coverage,
        "kpis": kpis,
        "trend": kpis[0] if kpis and kpis[0].get("series") else None,
        "breakdown": {"metric": main["name"], "label": main.get("label"), "dimension": by, **breakdown} if breakdown else None,
        "map": {"metric": main["name"], "label": main.get("label"), "dimension": geo_dimension, **place} if place else None,
        "standout": _standout(place or breakdown, main),
        "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    logger.info("home_built kpis=%s breakdown=%s map=%s", len(kpis), by, geo_dimension)
    return payload


# --- the briefing -----------------------------------------------------------------------------------------------------


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


def _briefing_figures(home: dict[str, Any]) -> tuple[list[dict[str, Any]], list[float]]:
    from app.ask_data.answer_checks import computed_figures

    rows: list[dict[str, Any]] = []
    extras: list[float] = []
    for kpi in home.get("kpis") or []:
        extras += [v for v in (kpi.get("value"), kpi.get("change"), kpi.get("change_pct")) if isinstance(v, (int, float))]
        rows += [{"month": p["month"], "metric_value": p["value"]} for p in kpi.get("series") or []]
    standout = home.get("standout") or {}
    extras += [float(g["difference"]) for g in standout.get("groups") or []] + [abs(float(g["difference"])) for g in standout.get("groups") or []]
    for kpi in home.get("kpis") or []:
        if isinstance(kpi.get("target"), (int, float)):
            extras += [float(kpi["target"]), kpi["value"] - float(kpi["target"]), float(kpi["target"]) - kpi["value"]]
        if kpi.get("previous_month"):
            extras.append(float(kpi["previous_month"]["value"]))
    for part in ("breakdown", "map"):
        block = home.get(part) or {}
        rows += list(block.get("rows") or [])
        if isinstance(block.get("overall_value"), (int, float)):
            extras.append(float(block["overall_value"]))
        extras += _numbers(computed_figures(list(block.get("rows") or []), block.get("overall_value")))
    return rows, extras


async def build_briefing(chat: Any, request: AskDataRequest, *, refresh: bool = False, language: str = "en") -> dict[str, Any]:
    """Three or four points a director should know, from the Home figures; a point whose figures are not in them is left out.
    Kept like Home, and rewritten when the figures it was written from were recomputed."""
    home = await build_home(chat, request, language=language)
    if not home.get("kpis"):
        return {"status": "no_data"}
    key = _key(chat, "briefing", language)
    kept = None if refresh else _read(chat, key)
    if kept is not None:
        if kept["payload"].get("for") != home.get("computed_at") or _age(kept) > FRESH_SECONDS:
            _in_background(key, _write_briefing(chat, request, home, key))
        return kept["payload"]
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        kept = None if refresh else _read(chat, key)
        if kept is not None:
            return kept["payload"]
        return await _write_briefing(chat, request, home, key)


async def _write_briefing(chat: Any, request: AskDataRequest, home: dict[str, Any], key: str) -> dict[str, Any]:
    from app.ask_data.answer_checks import computed_figures, unverified_figures

    language = home.get("language") or "en"
    facts: dict[str, Any] = {
        "language": language,
        "today": date.today().isoformat(),
        "data_coverage": home.get("data_coverage"),
        "kpis": [{k: v for k, v in kpi.items() if k != "description"} for kpi in home["kpis"]],
    }
    if home.get("standout"):
        facts["standout"] = home["standout"]
    for part in ("breakdown", "map"):
        block = home.get(part)
        if block:
            facts[part] = {
                "metric": block.get("label"),
                "unit": block.get("unit"),
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
    briefing = await provider.generate_structured(messages, Briefing, temperature=0.2, max_tokens=1000)
    rows, extras = _briefing_figures(home)

    def checked(text: str) -> bool:
        return bool(text.strip()) and not unverified_figures([text], rows, "", extras)

    if not checked(briefing.headline):
        logger.warning("home_briefing_headline_unverified")
        return {"status": "unverified"}
    look_next = [t for t in briefing.look_next if checked(t)][:3]
    dropped = (bool(briefing.what_happened) and not checked(briefing.what_happened)) + (bool(briefing.why_it_matters) and not checked(briefing.why_it_matters)) + (len(briefing.look_next) - len(look_next))
    if dropped:
        logger.info("home_briefing_parts_dropped count=%s", dropped)
    payload = {
        "status": "ok",
        "headline": briefing.headline.strip(),
        "what_happened": briefing.what_happened.strip() if checked(briefing.what_happened) else "",
        "why_it_matters": briefing.why_it_matters.strip() if checked(briefing.why_it_matters) else "",
        "look_next": look_next,
        "ask_next": [q for q in briefing.ask_next if q.strip()][:3],
        "language": language,
        "for": home.get("computed_at"),
    }
    _write(chat, key, payload)
    return payload


# --- ahead of the first viewer ----------------------------------------------------------------------------------------


async def warm(chat: Any) -> None:
    """Compute Home (and its briefing, when a model is assigned to Ask Data) so the first viewer does not wait."""
    assigned = None
    try:
        assigned = chat.assigned_model("ask_data")
    except Exception:  # noqa: BLE001
        assigned = None
    provider, model = (assigned.provider, assigned.id) if assigned is not None else ("qwen", "home-warm")
    request = AskDataRequest(session_id="home-warm", question="home", provider=provider, model=model)  # type: ignore[arg-type]
    try:
        home = await build_home(chat, request, refresh=True)
        logger.info("home_warmed status=%s", home.get("status"))
        if assigned is not None and home.get("kpis"):
            await build_briefing(chat, request, refresh=True)
            logger.info("home_briefing_warmed")
    except Exception:  # noqa: BLE001 - the first viewer computes it instead
        logger.exception("home_warm_failed")


def warm_soon(chat: Any, delay_seconds: float = 3.0) -> None:
    """Start warm() in the background (startup, after a publish)."""

    async def later() -> None:
        await asyncio.sleep(delay_seconds)
        await warm(chat)

    task = asyncio.create_task(later())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
