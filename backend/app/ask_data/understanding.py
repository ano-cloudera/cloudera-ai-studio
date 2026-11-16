"""Ask Data understanding by a language model: the question is read against the published semantic model, the way Genie or
Cortex Analyst read it, instead of by keyword scores and patterns.

The model receives the catalog of the active model (each metric with its description, synonyms and the breakdowns it supports;
each dimension with its name, synonyms and the real values found in the data) and today's date, and returns a structured intent:
the metric, the breakdown, whether by month, the filters with their values, the period, the order, how many rows, and the
language to answer in. Code only guards that intent: every name must exist in the catalog, a breakdown must be one the metric
supports, a filter value must be one the data holds, a period must be two valid dates. A choice that fails is sent back once
with what was wrong so the model corrects itself; whatever is still wrong is left out and said in a note. The governed SQL is
then compiled from the metric's own formula (SemanticContextService.compile_intent), so the model never writes a formula.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "understanding.md"
MAX_VALUES_SHOWN = 40


class _Lenient(BaseModel):
    # A model sometimes adds a field of its own; that must not throw away an otherwise good reading.
    model_config = ConfigDict(extra="ignore")


class IntentFilter(_Lenient):
    dimension: str = Field(description="The `key` of a dimension the metric supports.")
    values: list[str] = Field(default_factory=list, description="Values of that dimension, copied from its `values` when it lists them.")


class QueryIntent(_Lenient):
    metric: str = Field(default="", description="The `name` of the one metric the question asks for, or empty when none fits.")
    breakdown: list[str] = Field(default_factory=list, description="Dimension `key`s to group by, from the metric's `breakdowns`.")
    by_month: bool = Field(default=False, description="True when the question asks for a trend or a split by month.")
    filters: list[IntentFilter] = Field(default_factory=list)
    period_start: str | None = Field(default=None, description="First day of the period, YYYY-MM-DD, or null.")
    period_end: str | None = Field(default=None, description="The day after the last day of the period, YYYY-MM-DD, or null.")
    sort: Literal["desc", "asc"] = "desc"
    limit: int | None = Field(default=None, description="How many rows when the question asks for a top or bottom N, else null.")
    language: Literal["id", "en"] = Field(default="en", description="The language of the question: id for Indonesian, en for English.")
    clarification: str = Field(default="", description="A short question back to the user, only when no metric fits.")
    rationale: str = ""


def _time_keys(registry: Any, dataset: str) -> list[str]:
    from app.ask_data.intent_satisfaction import _time_dimension_keys

    return _time_dimension_keys(dataset, registry)


def _field(registry: Any, dataset: str, key: str) -> dict[str, Any]:
    return ((getattr(registry, "dataset_fields", None) or {}).get(dataset) or {}).get(key) or {}


def _dimension_entry(registry: Any, dataset: str, key: str, values: dict[tuple[str, str], list[str]]) -> dict[str, Any]:
    from app.ask_data.intent_satisfaction import dimension_display_name

    context = _field(registry, dataset, key).get("ai_context") or {}
    entry: dict[str, Any] = {"key": key, "name": dimension_display_name(registry, dataset, key)}
    if context.get("synonyms"):
        entry["synonyms"] = [str(s) for s in context["synonyms"]][:8]
    known = values.get((dataset, key))
    if known:
        entry["values"] = known[:MAX_VALUES_SHOWN]
        if len(known) > MAX_VALUES_SHOWN:
            entry["more_values"] = True
    return entry


def build_catalog(ctx: Any, values: dict[tuple[str, str], list[str]]) -> dict[str, Any]:
    """The published model as the model reads it: metrics, and the dimensions of each dataset with their real values."""
    from app.ask_data.metric_labels import humanize_metric_label

    registry = ctx.registry
    metrics: list[dict[str, Any]] = []
    dimensions: dict[str, dict[str, dict[str, Any]]] = {}
    for name in sorted(ctx.metrics):
        definition = ctx.metric_definition(name)
        dataset = str(definition.get("base_dataset") or "")
        times = set(_time_keys(registry, dataset))
        allowed = [str(k) for k in definition.get("allowed_dimensions") or []]
        context = definition.get("ai_context") if isinstance(definition.get("ai_context"), dict) else {}
        metrics.append({
            "name": name,
            "label": humanize_metric_label(name=name, definition=definition),
            "description": str(definition.get("description") or "")[:240],
            "synonyms": [str(s) for s in context.get("synonyms") or []][:8],
            "dataset": dataset,
            "breakdowns": [k for k in allowed if k not in times],
            "can_split_by_month": any(k in times for k in allowed),
        })
        for key in allowed:
            if key not in times:
                dimensions.setdefault(dataset, {})[key] = _dimension_entry(registry, dataset, key, values)
    return {"metrics": metrics, "dimensions": {ds: list(entries.values()) for ds, entries in dimensions.items()}}


async def dimension_values(ctx: Any, executor: Any, sources: dict[str, tuple[str, dict[str, Any]]]) -> dict[tuple[str, str], list[str]]:
    """The values of the low-cardinality text dimensions, read from the data (cached), so the model picks filters that exist.

    `sources` maps a dataset to its qualified table and the state the executor needs to reach it."""
    from app.ask_data.value_filters import _candidate_dimensions, _distinct_values

    registry = ctx.registry
    allowed_by_dataset: dict[str, set[str]] = {}
    for name in ctx.metrics:  # the dimensions the metrics of a dataset can be cut by
        definition = ctx.metric_definition(name)
        allowed_by_dataset.setdefault(str(definition.get("base_dataset") or ""), set()).update(str(k) for k in definition.get("allowed_dimensions") or [])
    jobs = []
    keys: list[tuple[str, str]] = []
    for dataset, (source, state) in sources.items():
        for key in _candidate_dimensions(registry, dataset, "", allowed_by_dataset.get(dataset, set())):
            jobs.append(_distinct_values(executor, state, source, ctx._registry_dimension_expression(dataset, key, "")))
            keys.append((dataset, key))
    found = await asyncio.gather(*jobs) if jobs else []
    return {key: sorted(v) for key, v in zip(keys, found) if v}


def _date(text: str | None) -> date | None:
    try:
        return date.fromisoformat(str(text)) if text else None
    except ValueError:
        return None


def _canonical(value: str, known: list[str]) -> str | None:
    folded = " ".join(str(value).casefold().split())
    return next((k for k in known if " ".join(k.casefold().split()) == folded), None)


def check(intent: QueryIntent, ctx: Any, values: dict[tuple[str, str], list[str]], *, pinned_metric: str | None = None, question: str = "") -> list[str]:
    """What is not valid in the intent, each said so the model can fix it."""
    problems: list[str] = []
    if pinned_metric and intent.metric != pinned_metric:
        problems.append(f"the metric must be '{pinned_metric}' (it was chosen for this step), not '{intent.metric}'")
    if not intent.metric:
        return problems if intent.clarification else [*problems, "no metric was chosen and no clarification question was written"]
    if intent.metric not in ctx.metrics:
        return [*problems, f"metric '{intent.metric}' is not in the catalog; use a `name` from `metrics`"]
    definition = ctx.metric_definition(intent.metric)
    dataset = str(definition.get("base_dataset") or "")
    times = set(_time_keys(ctx.registry, dataset))
    allowed = [str(k) for k in definition.get("allowed_dimensions") or []]
    supported = [k for k in allowed if k not in times]
    for key in intent.breakdown:
        if key not in supported:
            problems.append(f"breakdown '{key}' is not one '{intent.metric}' supports; its breakdowns are {supported}")
    single = {f.dimension for f in intent.filters if len(f.values) == 1}
    for key in intent.breakdown:
        if key in single:
            problems.append(
                f"breakdown '{key}' is also filtered to one value, so it gives a single row; break down by the dimension the question "
                "compares within that value, or leave the breakdown out"
            )
    filtered = {f.dimension for f in intent.filters}
    for key in supported:
        if key in filtered:
            continue
        named = _named_values(question, values.get((dataset, key)) or [])
        if named and (key in intent.breakdown or len(named) >= 2):
            problems.append(
                f"the question names {', '.join(repr(v) for v in named)}, which are values of '{key}', but there is no filter on '{key}', so every "
                f"other value of '{key}' is included. If the question is about those values, add the filter (values copied exactly), keeping "
                f"'{key}' in the breakdown when they are compared with each other. If they were only examples, keep it as it is."
            )
    for flt in intent.filters:
        if len({str(v).casefold() for v in flt.values}) >= 2 and flt.dimension in supported and flt.dimension not in intent.breakdown:
            problems.append(
                f"the filter on '{flt.dimension}' keeps {len(flt.values)} values, but '{flt.dimension}' is not in the breakdown, so their figures "
                "are added into one. If the question compares those values with each other (\"perbandingan\", \"bandingkan\", \"vs\"), add "
                f"'{flt.dimension}' to the breakdown, after the dimension they are compared across. If the question asks for them together, keep it as it is."
            )
    if intent.by_month and not any(k in times for k in allowed):
        problems.append(f"'{intent.metric}' cannot be split by month")
    for flt in intent.filters:
        if flt.dimension not in supported:
            problems.append(f"filter dimension '{flt.dimension}' is not one '{intent.metric}' supports; its breakdowns are {supported}")
            continue
        if not flt.values:
            problems.append(f"filter on '{flt.dimension}' has no values")
        known = values.get((dataset, flt.dimension))
        if known:
            for value in flt.values:
                if _canonical(value, known) is None:
                    problems.append(f"'{value}' is not a value of '{flt.dimension}'; its values are {known[:MAX_VALUES_SHOWN]}")
    start, end = _date(intent.period_start), _date(intent.period_end)
    if (intent.period_start or intent.period_end) and not (start and end and start < end):
        problems.append("the period needs both period_start and period_end as YYYY-MM-DD, with period_end after period_start")
    if intent.limit is not None and intent.limit < 1:
        problems.append("limit must be a positive number or null")
    return problems


def _sanitise(intent: QueryIntent, ctx: Any, values: dict[tuple[str, str], list[str]]) -> tuple[QueryIntent, list[str]]:
    """The intent with every part that is still not valid left out, and a note for each part left out."""
    indonesian = intent.language == "id"
    notes: list[str] = []
    if not intent.metric or intent.metric not in ctx.metrics:
        return intent.model_copy(update={"metric": ""}), notes
    definition = ctx.metric_definition(intent.metric)
    dataset = str(definition.get("base_dataset") or "")
    times = set(_time_keys(ctx.registry, dataset))
    supported = [str(k) for k in definition.get("allowed_dimensions") or [] if str(k) not in times]
    breakdown = [k for k in dict.fromkeys(intent.breakdown) if k in supported]
    for key in intent.breakdown:
        if key not in supported:
            notes.append(f"Pemecahan per {key} tidak tersedia untuk metrik ini, jadi tidak dipakai." if indonesian else f"A breakdown by {key} is not available for this metric, so it was left out.")
    filters: list[IntentFilter] = []
    for flt in intent.filters:
        if flt.dimension not in supported:
            notes.append(f"Filter {flt.dimension} tidak tersedia untuk metrik ini, jadi tidak dipakai." if indonesian else f"A filter on {flt.dimension} is not available for this metric, so it was left out.")
            continue
        known = values.get((dataset, flt.dimension))
        kept = [(_canonical(v, known) if known else v) for v in flt.values]
        missing = [v for v, k in zip(flt.values, kept) if k is None]
        kept = [k for k in kept if k]
        if missing:
            notes.append(
                f"{', '.join(missing)} tidak ditemukan di data, jadi tidak dipakai sebagai filter." if indonesian else f"{', '.join(missing)} was not found in the data, so it was not used as a filter."
            )
        if kept:
            filters.append(IntentFilter(dimension=flt.dimension, values=list(dict.fromkeys(kept))))
    start, end = _date(intent.period_start), _date(intent.period_end)
    period = (intent.period_start, intent.period_end) if start and end and start < end else (None, None)
    by_month = intent.by_month and bool(times & {str(k) for k in definition.get("allowed_dimensions") or []})
    limit = intent.limit if intent.limit and intent.limit > 0 else None
    return intent.model_copy(update={"breakdown": breakdown, "filters": filters, "period_start": period[0], "period_end": period[1], "by_month": by_month, "limit": limit}), notes


def to_resolution(intent: QueryIntent, ctx: Any, notes: list[str]) -> dict[str, Any]:
    """The intent as the resolution the workflow runs: the metric, the breakdown (the month first) and the intent itself."""
    if not intent.metric:
        text = intent.clarification or (
            "Metrik mana yang ingin Anda lihat? Sebutkan yang ingin diukur, misalnya volume atau tingkat keterlambatan."
            if intent.language == "id"
            else "Which measure would you like to see? Name what you want to measure."
        )
        return {"status": "needs_clarification", "reason": "understanding", "question": text, "context_mode": "GOVERNED_SEMANTIC", "understanding": intent.model_dump()}
    definition = ctx.metric_definition(intent.metric)
    dataset = str(definition.get("base_dataset") or "")
    time_key = None
    if intent.by_month:
        from app.ask_data.intent_satisfaction import pick_time_dimension

        time_key = pick_time_dimension(dataset, set(definition.get("allowed_dimensions") or []), ctx.registry)
    payload = {**intent.model_dump(), "time_key": time_key, "notes": notes}
    return {
        "status": "resolved",
        "metric": intent.metric,
        "matched_alias": "understanding",
        "definition": definition,
        "dimensions": [*([time_key] if time_key else []), *intent.breakdown],
        "dimension_mismatch": [],
        "intent": payload,
        "context_mode": "GOVERNED_SEMANTIC",
    }


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"[^0-9a-z]+", str(text).casefold()) if w]


def _mentioned(value: str, question: str) -> bool:
    """Whether the question names the value, in full or by a part or an abbreviation of it ("Jatim" for "Jatimbalinus")."""
    asked = [w for w in _words(question) if len(w) >= 4]
    return any(a.startswith(w) or w.startswith(a) for w in _words(value) for a in asked if len(w) >= 3)


def _named_values(question: str, known: list[str]) -> list[str]:
    """The values of a dimension that the question names as whole words ("Biosolar" in "Biosolar dan Pertalite"). A value inside a
    longer one that is also named ("Pertamax" in "Pertamax Turbo") is not counted."""
    text = " ".join(_words(question))
    found = [v for v in known if re.search(rf"(?<![0-9a-z]){re.escape(' '.join(_words(v)))}(?![0-9a-z])", text) and _words(v)]
    return [v for v in found if not any(v != other and " ".join(_words(v)) in " ".join(_words(other)) for other in found)]


def add_named_filters(intent: QueryIntent, question: str, ctx: Any, values: dict[tuple[str, str], list[str]]) -> tuple[QueryIntent, list[str]]:
    """Two or more values of a dimension that the question names, and that the reading splits by but does not filter, are the
    things being compared: the filter is added. (One name is left alone: a breakdown filtered to one value is a single row.)

    This follows the question's own words, after the model has been asked once; a model that keeps leaving the filter out would
    otherwise show every value of the dimension in a comparison of two."""
    if not intent.metric or intent.metric not in ctx.metrics or not intent.breakdown:
        return intent, []
    dataset = str(ctx.metric_definition(intent.metric).get("base_dataset") or "")
    filtered = {f.dimension for f in intent.filters}
    added: list[IntentFilter] = []
    notes: list[str] = []
    for key in intent.breakdown:
        if key in filtered:
            continue
        named = _named_values(question, values.get((dataset, key)) or [])
        if len(named) >= 2:
            added.append(IntentFilter(dimension=key, values=named))
            notes.append(
                f"{', '.join(named)} disebut di pertanyaan, jadi hanya itu yang dibandingkan." if intent.language == "id" else f"{', '.join(named)} named in the question, so only those are compared."
            )
    if not added:
        return intent, []
    logger.info("understanding_named_filters_added question=%r added=%s", question[:160], [(f.dimension, f.values) for f in added])
    return intent.model_copy(update={"filters": [*intent.filters, *added]}), notes


def drop_carried_filters(intent: QueryIntent, question: str, conversation: list[dict[str, Any]] | None) -> tuple[QueryIntent, list[str]]:
    """A filter whose value is named in the earlier conversation but nowhere in the question was copied from it, not asked for.

    The question is already written out in full, so what it limits itself to is in it. A value named only in the conversation
    ("Sulawesi", from a turn before) would silently narrow a question that asks about everything."""
    if not conversation or not intent.filters:
        return intent, []
    history = json.dumps(conversation[-4:], ensure_ascii=False, default=str).casefold()
    kept: list[IntentFilter] = []
    notes: list[str] = []
    indonesian = intent.language == "id"
    for flt in intent.filters:
        values = [v for v in flt.values if _mentioned(str(v), question) or " ".join(str(v).casefold().split()) not in history]
        for value in (v for v in flt.values if v not in values):
            notes.append(f"{value} hanya disebut di percakapan sebelumnya, jadi tidak dipakai sebagai filter." if indonesian else f"{value} was named only earlier in the conversation, so it was not used as a filter.")
        if values:
            kept.append(IntentFilter(dimension=flt.dimension, values=values))
    if not notes:
        return intent, []
    logger.info("understanding_carried_filters_dropped question=%r dropped=%s", question[:160], notes)
    return intent.model_copy(update={"filters": kept}), notes


async def understand(
    provider: Any,
    *,
    question: str,
    ctx: Any,
    values: dict[tuple[str, str], list[str]],
    pinned_metric: str | None = None,
    conversation: list[dict[str, Any]] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """The resolution of a data question, read by the language model and checked by code (one self-correction round)."""
    payload: dict[str, Any] = {
        "question": question,
        "today": (today or date.today()).isoformat(),
        "catalog": build_catalog(ctx, values),
    }
    if pinned_metric:
        payload["metric_to_use"] = pinned_metric
    if conversation:
        payload["conversation"] = conversation[-4:]
    messages: list[dict[str, str]] = [
        {"role": "system", "content": PROMPT.read_text(encoding="utf-8")},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
    ]
    intent = await provider.generate_structured(messages, QueryIntent, temperature=0.0, max_tokens=700)
    problems = check(intent, ctx, values, pinned_metric=pinned_metric, question=question)
    if problems:
        logger.info("understanding_repair question=%r problems=%s", question[:160], problems)
        messages += [
            {"role": "assistant", "content": intent.model_dump_json()},
            {"role": "user", "content": "These choices are not valid:\n- " + "\n- ".join(problems) + "\nReturn the corrected JSON, using only names and values from the catalog."},
        ]
        try:
            intent = await provider.generate_structured(messages, QueryIntent, temperature=0.0, max_tokens=700)
        except Exception:  # noqa: BLE001 - the first reading is still checked below
            logger.warning("understanding_repair_failed")
    if pinned_metric and intent.metric != pinned_metric and pinned_metric in ctx.metrics:
        intent = intent.model_copy(update={"metric": pinned_metric})
    intent, notes = _sanitise(intent, ctx, values)
    intent, carried = drop_carried_filters(intent, question, conversation)
    intent, named = add_named_filters(intent, question, ctx, values)
    notes = [*notes, *carried, *named]
    logger.info(
        "understanding question=%r metric=%s breakdown=%s by_month=%s filters=%s period=%s..%s language=%s notes=%s",
        question[:160], intent.metric, intent.breakdown, intent.by_month, [(f.dimension, f.values) for f in intent.filters],
        intent.period_start, intent.period_end, intent.language, notes,
    )
    return to_resolution(intent, ctx, notes)
