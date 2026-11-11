"""Agent mode: an open question is split into steps that each run through the normal governed pipeline.

A planner (the language model, limited to the metrics of the published semantic model and the document libraries) writes
the steps. Each data step is an ordinary Ask Data question, so governed compilation, comparisons and checks all apply; each
knowledge step is an ordinary document question. A final call writes the report from those results. A plan of fewer than two
steps (or a failed plan call) is completed from the metric catalog; only when no step answers does the normal answer stand.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import date
from pathlib import Path
from time import perf_counter
from typing import Any, AsyncIterator, Literal

from pydantic import BaseModel, ConfigDict

from app.ask_data.calculation_note import readable_name
from app.core.language import detect_language
from app.core.models import (
    AnalysisOutput,
    AskDataRequest,
    AskDataResponse,
    CalculationCheck,
    CalculationNote,
    ChatContextSource,
    CitationRecord,
    LlmUsage,
    QueryData,
    Timings,
)

logger = logging.getLogger(__name__)

PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"
MAX_STEPS = 5
MAX_ROWS_PER_STEP = 30  # a breakdown by terminal or province fits whole, so a low-volume group is not cut off

# Questions one figure or one table cannot answer: why, what to do, an overview or summary, how two things relate.
# The conversation reading (an LLM call) recognises them in other words too; this is the part that needs no model.
_OPEN_QUESTION = re.compile(
    r"\b(why|how come|root cause|what (?:is|are) (?:the )?(?:cause|reason|driver)s?|what(?:'s| is) driving|what should (?:we|i)|where should (?:we|i) (?:start|focus)"
    r"|how (?:can|could|do|should) (?:we|i) (?:improve|reduce|fix|increase|lower|raise|optimi[sz]e)|recommend\w*|diagnos\w*|investigat\w*|deep[- ]dive"
    r"|(?:give|write|make|prepare) (?:me )?(?:an? )?(?:summary|overview|report|brief)|summari[sz]e|executive summary|overall performance|how (?:are|is) (?:we|our \w+) doing"
    r"|correlat\w*|relationship between|impact of"
    r"|kenapa|mengapa|kok bisa|apa (?:sebab|alasan)(?:nya)?|penyebab\w*|faktor\w*|pemicu\w*|akar masalah"
    r"|apa yang (?:harus|perlu|sebaiknya|bisa) (?:kita|saya|dilakukan)|harus (?:ngapain|apa)|sebaiknya|mulai dari mana|fokus (?:ke|di) mana|prioritas\w*"
    r"|(?:cara )?(?:memperbaiki|perbaiki|meningkatkan|tingkatkan|mengurangi|kurangi|menurunkan|turunkan|mengoptimalkan|optimalkan)"
    r"|rekomendasi\w*|saran(?:nya)?|analisis mendalam|analisa mendalam|investigasi|telusuri"
    r"|rangkuman|rangkum\w*|ringkas\w*|laporan untuk|insight\w*|temuan utama"
    r"|(?:performa|kinerja|kondisi|kesehatan)\b[^?.]{0,40}\b(?:keseluruhan|secara umum|overall)"
    r"|hubungan(?:nya)?|korelasi|berpengaruh|pengaruh(?:nya)?|dampak(?:nya)?)\b",
    re.I,
)


def is_open_question(question: str) -> bool:
    return bool(_OPEN_QUESTION.search(question or ""))


# An overview asks for the state of things, not for one figure: it is answered with the figures the author marked as headline.
_OVERVIEW = re.compile(
    r"\b(overall|overview|summary|summari[sz]e|how (?:are|is) (?:we|our \w+) doing|keseluruhan|secara umum|ringkasan|rangkuman|"
    r"(?:performa|kinerja|kondisi|kesehatan)\b)",
    re.I,
)


def _headline_metrics(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted((m for m in catalog if m.get("name") and m.get("headline")), key=lambda m: int(m["headline"]))


def _labels(language: str) -> dict[str, str]:
    if language == "id":
        return {"plan": "Merencanakan analisis", "step": "Langkah {i} dari {n}: {what}", "report": "Menyusun jawaban"}
    return {"plan": "Planning the analysis", "step": "Step {i} of {n}: {what}", "report": "Writing the report"}


class _Lenient(BaseModel):
    # A small model sometimes adds a field of its own; that must not throw away an otherwise good plan.
    model_config = ConfigDict(extra="ignore")


class AgentStep(_Lenient):
    kind: Literal["data", "knowledge"]
    question: str
    why: str = ""
    metric: str = ""  # the exact name of a catalog metric for a data step; it pins the step so no metric question comes up


class AgentPlan(_Lenient):
    steps: list[AgentStep]


def _prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def _metric_names(catalog: list[dict[str, Any]]) -> set[str]:
    return {str(item.get("name")) for item in catalog if item.get("name")}


def _humanize_catalog(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for item in catalog:
        dims = [readable_name(str(d)) for d in item.get("allowed_dimensions") or []]
        entry = {"metric": item.get("name"), "description": str(item.get("description") or "")[:160], "breakdowns": dims[:24]}
        if item.get("headline"):
            entry["headline"] = int(item["headline"])  # the author marked it as one of the figures the business watches most (1 first)
        out.append(entry)
    return out


async def plan_steps(
    provider: Any,
    *,
    question: str,
    catalog: list[dict[str, Any]],
    has_knowledge: bool,
    conversation: list[dict[str, Any]] | None = None,
    data_coverage: str | None = None,
) -> list[AgentStep]:
    import json

    payload: dict[str, Any] = {
        "question": question,
        "language": detect_language(question),
        "metric_catalog": _humanize_catalog(catalog),
        "documents_available": has_knowledge,
        "today": date.today().isoformat(),
    }
    if conversation:
        payload["conversation"] = conversation
    if data_coverage:
        payload["data_coverage"] = data_coverage
    plan = await provider.generate_structured(
        [{"role": "system", "content": _prompt("agent_planner.md")}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)}],
        AgentPlan,
        temperature=0.1,
        max_tokens=1200,
    )
    steps = _clean_steps(plan.steps, has_knowledge, metrics=_metric_names(catalog))[:MAX_STEPS]
    headline = {str(m["name"]) for m in _headline_metrics(catalog)}
    if headline and _OVERVIEW.search(question or "") and not any(s.metric in headline for s in steps if s.kind == "data"):
        # An overview that leaves out every headline figure (it asked for price and value, not the late rate) is replaced by the
        # plan built from them.
        logger.info("agent_plan_overview_without_headline kept=%s", len(steps))
        steps = fallback_steps(question, catalog, [], detect_language(question), prefer_headline=True)[:MAX_STEPS]
    if headline and _OVERVIEW.search(question or ""):
        steps = _with_breakdown(steps, catalog, detect_language(question))
    logger.info(
        "agent_plan raw=%s kept=%s steps=%r",
        len(plan.steps),
        len(steps),
        [(s.kind, s.metric or "-", s.question[:120]) for s in steps],
    )
    return steps


_RATE = re.compile(r"\b(rate|ratio|share|percent\w*|persen\w*|tingkat)\b|%", re.I)
_VOLUME = re.compile(r"\b(total|number of|count|jumlah|banyaknya)\b", re.I)
_NOT_A_GROUP = re.compile(r"(_id$|date|time|_at$|days?$|hours?$|value|amount|items|qty|quantity|_is_|^is_|_flag|tanggal|bulan|periode|waktu|tahun)", re.I)
_TIME_DIMENSION = re.compile(r"date|month|period|time|tanggal|bulan|periode|waktu", re.I)
_QUESTION_WORDS = {
    "pengiriman": "delivery shipment shipments", "kirim": "delivery shipment", "telat": "late", "terlambat": "late", "keterlambatan": "late",
    "pesanan": "order orders", "order": "order orders", "batal": "cancel cancelled cancellation", "dibatalkan": "cancel cancelled cancellation",
    "penjualan": "sales order value", "pendapatan": "revenue value", "kurir": "carrier", "gudang": "warehouse",
}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.casefold()) if len(w) > 2}


def _dataset_key(item: dict[str, Any]) -> tuple[str, ...]:
    return tuple(sorted(str(d) for d in item.get("allowed_dimensions") or []))


def _is_rate(item: dict[str, Any]) -> bool:
    return bool(_RATE.search(f"{readable_name(str(item.get('name') or ''))} {item.get('description') or ''}"))


def _is_volume(item: dict[str, Any]) -> bool:
    return not _is_rate(item) and bool(_VOLUME.search(f"{readable_name(str(item.get('name') or ''))} {item.get('description') or ''}"))


def fallback_steps(
    question: str,
    catalog: list[dict[str, Any]],
    seed: list[AgentStep],
    language: str,
    *,
    current_metric: str | None = None,
    prefer_headline: bool = False,
) -> list[AgentStep]:
    """The plan an analyst would start from when the planner gave fewer than two steps: the headline figure, the volume
    behind it (or the second metric the question names), its trend by month and the group that stands out. Built only
    from catalog metrics and their breakdowns. The metric is the planner's, else the one the question names, else the
    one the conversation is about (`current_metric`), else the first rate."""
    metrics = [item for item in catalog if item.get("name")]
    if not metrics:
        return list(seed)
    by_name = {str(item["name"]): item for item in metrics}
    asked = _words(question)
    asked |= {w for word in list(asked) for w in _QUESTION_WORDS.get(word, "").split()}
    scored = sorted(
        ((len(asked & _words(f"{readable_name(str(m['name']))} {m.get('description') or ''}")), _is_rate(m), -i, m) for i, m in enumerate(metrics)),
        key=lambda t: t[:3],
        reverse=True,
    )
    named = [t[3] for t in scored if t[0] > 0]
    main = next((by_name[s.metric] for s in seed if s.kind == "data" and s.metric in by_name), None)
    headline = _headline_metrics(metrics)
    if main is None and prefer_headline and headline:
        main = next((m for m in headline if _is_rate(m)), headline[0])
    if main is None:
        main = (named[0] if named else None) or by_name.get(current_metric or "") or next((m for m in metrics if _is_rate(m)), metrics[0])
    same = [m for m in metrics if _dataset_key(m) == _dataset_key(main)]
    rate = main if _is_rate(main) else next((m for m in same if _is_rate(m)), main)
    # A second rate the question names on other data ("dibatalkan ... keterlambatan") is checked next to the first.
    other = next((m for m in named if m is not main and m is not rate and _is_rate(m) and _dataset_key(m) != _dataset_key(main)), None)
    volume = (
        other
        or next((m for m in headline if m in same and not _is_rate(m) and m is not main), None)
        or next((m for m in same if _is_volume(m) and m is not main), None)
    )
    dims = [str(d) for d in rate.get("allowed_dimensions") or []]
    has_time = any(_TIME_DIMENSION.search(d) for d in dims)
    groups = [d for d in dims if not _NOT_A_GROUP.search(d)]
    ind = language == "id"

    def label(item: dict[str, Any]) -> str:
        return readable_name(str(item["name"]))

    def group_label(key: str) -> str:
        words = readable_name(key).split()
        # "delivery shipments region name" -> "region": drop the dataset words the metric already names.
        words = words[2:] if len(words) > 2 else words
        if len(words) > 1 and words[-1].casefold() == "name":
            words = words[:-1]
        return " ".join(words)

    steps: list[AgentStep] = list(seed[:1]) if seed and seed[0].kind == "data" else []
    if not steps:
        steps.append(AgentStep(kind="data", question=label(main), why="Angka utama" if ind else "The headline figure", metric=str(main["name"])))
    if rate is not main:
        steps.append(AgentStep(kind="data", question=label(rate), why="Rasio utama" if ind else "The main rate", metric=str(rate["name"])))
    if volume is not None:
        why = ("Metrik kedua yang ditanyakan" if ind else "The other metric asked about") if volume is other else ("Volume di baliknya" if ind else "The volume behind it")
        steps.append(AgentStep(kind="data", question=label(volume), why=why, metric=str(volume["name"])))
    if has_time:
        steps.append(AgentStep(kind="data", question=f"{label(rate)} per {'bulan' if ind else 'month'}", why="Tren per bulan" if ind else "The trend by month", metric=str(rate["name"])))
    if groups:
        group = group_label(groups[0])
        steps.append(AgentStep(kind="data", question=f"{label(rate)} per {group}", why=(f"{group} yang paling menonjol" if ind else f"The {group} that stands out"), metric=str(rate["name"])))
    return _clean_steps(steps, False, metrics=set(by_name))[:4]


def _with_breakdown(steps: list[AgentStep], catalog: list[dict[str, Any]], language: str) -> list[AgentStep]:
    """An overview names the group that stands out, so it needs one step by a group. When the plan has none, the main headline rate
    by its first non-time dimension is added, in place of the first step that is not a headline metric (else the last step)."""
    by_name = {str(m["name"]): m for m in catalog if m.get("name")}
    data = [s for s in steps if s.kind == "data"]
    if any(re.search(r"\bper\s+(?!bulan\b|month\b|tahun\b|year\b)\w", s.question, re.I) for s in data):
        return steps
    headline = _headline_metrics(catalog)
    rate = next((m for m in headline if _is_rate(m)), None)
    if rate is None:
        return steps
    groups = [str(d) for d in rate.get("allowed_dimensions") or [] if not _NOT_A_GROUP.search(str(d))]
    if not groups:
        return steps
    words = readable_name(groups[0]).split()
    words = words[2:] if len(words) > 2 else words
    if len(words) > 1 and words[-1].casefold() == "name":
        words = words[:-1]
    group = " ".join(words)
    added = AgentStep(
        kind="data",
        question=f"{readable_name(str(rate['name']))} per {group}",
        why=f"{group} yang paling menonjol" if language == "id" else f"The {group} that stands out",
        metric=str(rate["name"]),
    )
    headline_names = {str(m["name"]) for m in headline}
    kept = list(steps)
    if len(data) >= 4:
        drop = next((s for s in kept if s.kind == "data" and s.metric not in headline_names), data[-1])
        kept.remove(drop)
    return [*kept, added]


def _clean_steps(
    raw: list[AgentStep],
    has_knowledge: bool,
    *,
    taken: list[AgentStep] | None = None,
    metrics: set[str] | None = None,
) -> list[AgentStep]:
    """Drop duplicates, a second or unavailable knowledge step and more than four data steps; `taken` are steps already run."""
    steps: list[AgentStep] = []
    seen = {" ".join(t.question.split()).casefold() for t in taken or []}
    data_steps = sum(1 for t in taken or [] if t.kind == "data")
    knowledge_taken = any(t.kind == "knowledge" for t in taken or [])
    for step in raw:
        text = " ".join(step.question.split())
        if not text or text.casefold() in seen:
            continue
        if step.kind == "knowledge" and (not has_knowledge or knowledge_taken or any(s.kind == "knowledge" for s in steps)):
            continue
        if step.kind == "data":
            data_steps += 1
            if data_steps > 4:
                continue
        seen.add(text.casefold())
        pinned = step.metric.strip() if step.kind == "data" and (metrics is None or step.metric.strip() in metrics) else ""
        steps.append(AgentStep(kind=step.kind, question=text, why=" ".join(step.why.split())[:160], metric=pinned))
    return steps


class AgentRefinement(_Lenient):
    steps: list[AgentStep]


async def refine_steps(
    provider: Any,
    *,
    question: str,
    catalog: list[dict[str, Any]],
    has_knowledge: bool,
    done: list[dict[str, Any]],
    remaining: list[AgentStep],
) -> list[AgentStep]:
    """The remaining steps, adjusted to what the first result showed. Never more than planned; any failure keeps the plan."""
    import json

    try:
        payload = {
            "question": question,
            "metric_catalog": _humanize_catalog(catalog),
            "documents_available": has_knowledge,
            "done": done,
            "planned": [{"kind": s.kind, "question": s.question, "why": s.why} for s in remaining],
        }
        refined = await provider.generate_structured(
            [{"role": "system", "content": _prompt("agent_refine.md")}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)}],
            AgentRefinement,
            temperature=0.1,
            max_tokens=500,
        )
        steps = _clean_steps(list(refined.steps), has_knowledge, metrics=_metric_names(catalog))[: len(remaining)]
        return steps or remaining
    except Exception:  # noqa: BLE001 - the original plan is always a valid answer
        logger.warning("agent_refine_failed")
        return remaining


def _step_result(index: int, step: AgentStep, response: AskDataResponse | None, error: str | None = None) -> dict[str, Any]:
    base: dict[str, Any] = {"step": index, "kind": step.kind, "question": step.question}
    if response is None or response.status != "SUCCESS":
        return {**base, "status": "failed", "error": error or (response.answer.direct_answer[:200] if response else "no answer")}
    result = {**base, "status": "ok", "answer": response.answer.direct_answer, "caveats": list(response.answer.caveats)[:2]}
    if step.kind == "data":
        result.update(
            metric=response.data.governed_metric_display_name or response.data.governed_metric,
            columns=list(response.data.columns),
            rows=list(response.data.rows[:MAX_ROWS_PER_STEP]),
            row_count=response.data.row_count,
        )
        if response.data.overall_value is not None:
            result["overall_value"] = response.data.overall_value
        if response.calculation and response.calculation.scope:
            result["scope"] = response.calculation.scope
    else:
        result["sources"] = [
            {"file": c.filename, "page": c.page_number, "snippet": c.snippet[:300]} for c in (response.citations or [])[:4]
        ]
    return result


def _usage_sum(responses: list[AskDataResponse]) -> LlmUsage:
    total = LlmUsage()
    for response in responses:
        if response.usage:
            total = LlmUsage(
                prompt_tokens=total.prompt_tokens + response.usage.prompt_tokens,
                completion_tokens=total.completion_tokens + response.usage.completion_tokens,
                total_tokens=total.total_tokens + response.usage.total_tokens,
                llm_calls=total.llm_calls + response.usage.llm_calls,
            )
    return total


def _step_line(index: int, step: AgentStep, response: AskDataResponse | None) -> str:
    label = "Data" if step.kind == "data" else "Documents"
    if response is None or response.status != "SUCCESS":
        return f"{index}. {label}: {step.question} (no answer)"
    if step.kind == "data" and response.calculation:
        return f"{index}. {label}: {step.question} - {response.calculation.summary}"
    if step.kind == "knowledge":
        files = ", ".join(dict.fromkeys(c.filename or "document" for c in (response.citations or [])))
        return f"{index}. {label}: {step.question}" + (f" - {files}" if files else "")
    return f"{index}. {label}: {step.question}"


def primary_index(steps: list[AgentStep], responses: list[AskDataResponse | None]) -> int | None:
    """The data step whose table and chart are shown: a breakdown with a chart, else one with several rows, else the first."""
    data_done = [i for i, (s, r) in enumerate(zip(steps, responses)) if s.kind == "data" and r is not None and r.status == "SUCCESS"]
    for test in (lambda r: r.data.row_count > 1 and r.chart_spec, lambda r: r.data.row_count > 1):
        for i in data_done:
            if test(responses[i]):
                return i
    return data_done[0] if data_done else None


def assemble_response(
    *,
    request: AskDataRequest,
    steps: list[AgentStep],
    responses: list[AskDataResponse | None],
    analysis: AnalysisOutput,
    elapsed_ms: float,
) -> AskDataResponse:
    done = [(s, r) for s, r in zip(steps, responses) if r is not None and r.status == "SUCCESS"]
    data_done = [(s, r) for s, r in done if s.kind == "data"]
    index = primary_index(steps, responses)
    primary = responses[index] if index is not None else None
    citations: list[CitationRecord] = [c for s, r in done if s.kind == "knowledge" for c in (r.citations or [])]
    warnings = list(dict.fromkeys(c.message for _, r in data_done if r.calculation for c in r.calculation.checks if c.status == "warning"))
    note = CalculationNote(
        kind="agent",
        summary=f"{len(data_done)} data check{'s' if len(data_done) != 1 else ''}" + (f" and {len(done) - len(data_done)} document lookup" if len(done) > len(data_done) else ""),
        steps=[_step_line(i + 1, s, r) for i, (s, r) in enumerate(zip(steps, responses))],
        source=list(dict.fromkeys(t for _, r in data_done if r.calculation for t in r.calculation.source)),
        checks=[CalculationCheck(name="steps", status="warning", message=m) for m in warnings],
    )
    usage = _usage_sum([r for r in responses if r is not None])
    return AskDataResponse(
        request_id=str(uuid.uuid4()),
        session_id=request.session_id,
        status="SUCCESS",
        provider=request.provider,
        model=request.model,
        strategy="agent",
        answer=analysis,
        data=primary.data if primary else QueryData(),
        chart_spec=primary.chart_spec if primary else None,
        timings=Timings(total_ms=elapsed_ms),
        usage=usage if usage.llm_calls else None,
        governed_sql=primary.governed_sql if primary else None,
        route="ask_data",
        citations=citations or None,
        semantic_runtime=primary.semantic_runtime if primary else None,
        calculation=note,
    )


class AskDataAgent:
    def __init__(self, chat_service: Any) -> None:
        self._chat = chat_service

    def applicable(self, request: AskDataRequest) -> bool:
        """Whether the agent may look at the question at all; whether it takes it is decided after reading the turn."""
        from app.core.config import get_settings

        return bool(get_settings().agent_mode_enabled) and request.mode == "ask_data"

    def _knowledge_library_ids(self) -> list[str]:
        return self._chat.ready_library_ids()

    async def _read(self, request: AskDataRequest) -> tuple[str | None, list[dict[str, Any]]]:
        """The question written out in full when it is one for the agent, else None. A follow-up such as "kenapa bisa
        setinggi itu?" is read against the conversation first, so the plan knows which metric and group it is about."""
        reader = getattr(self._chat, "read_conversation", None)
        reading, history = None, []
        if reader is not None:
            try:
                reading, history = await reader(request)
            except Exception:  # noqa: BLE001 - without a reading the question is used as written
                logger.exception("agent_read_failed")
        if reading is not None and reading.is_conversational:
            return None, history
        question = (reading.standalone_question if reading else "") or request.question
        wanted = (reading is not None and reading.kind == "analysis") or is_open_question(question) or is_open_question(request.question)
        if not wanted:
            return None, history
        logger.info("agent_mode_taken kind=%s question=%r", getattr(reading, "kind", None), question[:200])
        return question, history

    async def stream(self, request: AskDataRequest) -> AsyncIterator[dict[str, Any]]:
        """Progress events, then {"type": "done", "response": ...}; yields nothing at all when agent mode does not apply."""
        if not self.applicable(request):
            return
        started = perf_counter()
        language = detect_language(request.question)
        labels = _labels(language)
        catalog: list[dict[str, Any]] = []
        question = None
        try:
            prepared, provider = self._chat.provider_for(request)
            question, history = await self._read(prepared)
            if question is None:
                return
            catalog = self._chat.metric_catalog()
            library_ids = self._knowledge_library_ids()
            if not catalog:
                logger.warning("agent_fallback reason=no_metric_catalog")
                return
            from app.ask_data.answer_context import coverage_label, known_coverage
            from app.ask_data.conversation import previous_turns

            coverage = coverage_label(known_coverage(), language)
            yield {"type": "progress", "stage": "agent_plan", "label": labels["plan"]}
            steps = await plan_steps(
                provider,
                question=question,
                catalog=catalog,
                has_knowledge=bool(library_ids),
                conversation=previous_turns(history)[-2:] if history else None,
                data_coverage=coverage,
            )
        except Exception:  # noqa: BLE001 - a plan built from the catalog follows
            logger.exception("agent_plan_failed")
            if not question or not catalog:
                return
            steps = []
        if len(steps) < 2:
            from app.ask_data.conversation import last_metric

            steps = fallback_steps(question, catalog, steps, language, current_metric=last_metric(history) if history else None, prefer_headline=bool(_OVERVIEW.search(question)))
            logger.warning("agent_plan_fallback steps=%r", [(s.metric, s.question) for s in steps])
        if len(steps) < 2:
            logger.warning("agent_fallback reason=plan_has_%s_step", len(steps))
            return
        responses: list[AskDataResponse | None] = []
        run_id = uuid.uuid4().hex[:8]
        index = 0
        while index < len(steps):
            step = steps[index]
            index += 1
            yield {"type": "progress", "stage": "agent_step", "label": labels["step"].format(i=index, n=len(steps), what=step.why or step.question), "detail": step.question}
            pinned = (
                [ChatContextSource(type="semantic_metric", id=step.metric, name=step.metric)]
                if step.kind == "data" and step.metric and step.metric in _metric_names(catalog)
                else prepared.context_sources
            )
            sub = prepared.model_copy(
                update={
                    "session_id": f"agent-{run_id}-{index}",
                    "question": step.question,
                    "mode": "rag" if step.kind == "knowledge" else "ask_data",
                    "library_ids": library_ids if step.kind == "knowledge" else None,
                    "context_sources": pinned,
                }
            )
            try:
                responses.append(await self._chat.run(sub))
            except Exception:  # noqa: BLE001 - one failing step must not stop the others
                logger.exception("agent_step_failed step=%s", index)
                responses.append(None)
            failed = responses[-1] is None or responses[-1].status not in ("SUCCESS", "NO_DATA")
            if failed and step.kind == "data" and pinned is not prepared.context_sources:
                # The pin is a help, not a requirement: the same question without it goes through the normal metric choice.
                logger.warning("agent_step_unpinned step=%s metric=%s", index, step.metric)
                try:
                    responses[-1] = await self._chat.run(sub.model_copy(update={"context_sources": prepared.context_sources}))
                except Exception:  # noqa: BLE001
                    logger.exception("agent_step_failed step=%s unpinned", index)
            last = responses[-1]
            logger.info(
                "agent_step step=%s status=%s strategy=%s rows=%s question=%r",
                index, getattr(last, "status", None), getattr(last, "strategy", None), getattr(getattr(last, "data", None), "row_count", None), step.question[:120],
            )
            first = responses[0]
            if index == 1 and len(steps) > 2 and first is not None and first.status == "SUCCESS" and step.kind == "data":
                steps = [step, *await refine_steps(provider, question=question, catalog=catalog, has_knowledge=bool(library_ids), done=[_step_result(1, step, first)], remaining=steps[1:])]
        if not any(r is not None and r.status == "SUCCESS" and s.kind == "data" for s, r in zip(steps, responses)):
            logger.warning("agent_fallback reason=no_step_answered statuses=%s", [getattr(r, "status", None) for r in responses])
            return  # nothing to report: let the normal pipeline answer
        yield {"type": "progress", "stage": "agent_report", "label": labels["report"]}
        try:
            import json

            _, provider = self._chat.provider_for(request)  # each step cleared the model context
            results = [_step_result(i + 1, s, r) for i, (s, r) in enumerate(zip(steps, responses))]
            coverage = next((r.data.data_coverage for r in responses if r is not None and r.data.data_coverage), None)
            payload: dict[str, Any] = {"question": request.question, "language": language, "steps": results}
            if question != request.question:
                payload["question_in_full"] = question
            if coverage:
                payload["data_coverage"] = coverage_label(coverage, language)
            analysis = await provider.generate_structured(
                [
                    {"role": "system", "content": _prompt("agent_report.md")},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
                ],
                AnalysisOutput,
                temperature=0.2,
                max_tokens=2000,
            )
        except Exception:  # noqa: BLE001
            logger.exception("agent_report_failed")
            return
        discard = getattr(self._chat, "discard_reading", None)
        if discard is not None:
            discard(prepared)
        shown = primary_index(steps, responses)
        frame = self._step_frames(run_id, len(steps), shown, request=request, question=question)
        settle = getattr(self._chat, "settle_follow_ups", None)
        if settle is not None:
            try:
                analysis = settle(
                    analysis,
                    asked=question,
                    metric=(frame or {}).get("metric"),
                    dimensions=(frame or {}).get("dimensions"),
                )
            except Exception:  # noqa: BLE001
                logger.exception("agent_follow_ups_failed")
        # The model that ran (a registry assignment may differ from the one the UI sent), as a normal answer reports it.
        response = assemble_response(request=prepared, steps=steps, responses=responses, analysis=analysis, elapsed_ms=round((perf_counter() - started) * 1000, 3))
        response = self._chat.finalize_response(response)
        if frame:
            self._chat.record_turn(prepared, response, frame=frame)
        else:
            self._chat.record_turn(prepared, response)
        yield {"type": "done", "response": response}

    def _step_frames(self, run_id: str, count: int, shown: int | None, *, request: AskDataRequest, question: str) -> dict[str, Any] | None:
        """The turn memory of the step whose table is shown, so a follow-up ("and per carrier?") continues it; the
        steps' own sessions are removed."""
        reader = getattr(self._chat, "step_frame", None)
        if reader is None:
            return None
        frame = None
        for i in range(count):
            got = reader(f"agent-{run_id}-{i + 1}")
            if i == shown:
                frame = got
        if not frame:
            return None
        return {**frame, "question": request.question.strip(), "standalone_question": question}

    async def run(self, request: AskDataRequest) -> AskDataResponse | None:
        final = None
        async for event in self.stream(request):
            if event.get("type") == "done":
                final = event["response"]
        return final
