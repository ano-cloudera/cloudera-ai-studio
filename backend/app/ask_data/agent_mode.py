"""Agent mode: an open question is split into steps that each run through the normal governed pipeline.

A planner (the language model, limited to the metrics of the published semantic model and the document libraries) writes
the steps. Each data step is an ordinary Ask Data question, so governed compilation, comparisons and checks all apply; each
knowledge step is an ordinary document question. A final call writes the report from those results. If the planner fails
or finds one step enough, nothing here changes the normal answer.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import date
from pathlib import Path
from time import perf_counter
from typing import Any, AsyncIterator, Literal

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
    StrictModel,
    Timings,
)

logger = logging.getLogger(__name__)

PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"
MAX_STEPS = 5
MAX_ROWS_PER_STEP = 15

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


def _labels(language: str) -> dict[str, str]:
    if language == "id":
        return {"plan": "Merencanakan analisis", "step": "Langkah {i} dari {n}: {what}", "report": "Menyusun jawaban"}
    return {"plan": "Planning the analysis", "step": "Step {i} of {n}: {what}", "report": "Writing the report"}


class AgentStep(StrictModel):
    kind: Literal["data", "knowledge"]
    question: str
    why: str = ""
    metric: str = ""  # the exact name of a catalog metric for a data step; it pins the step so no metric question comes up


class AgentPlan(StrictModel):
    steps: list[AgentStep]


def _prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def _metric_names(catalog: list[dict[str, Any]]) -> set[str]:
    return {str(item.get("name")) for item in catalog if item.get("name")}


def _humanize_catalog(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for item in catalog:
        dims = [readable_name(str(d)) for d in item.get("allowed_dimensions") or []]
        out.append({"metric": item.get("name"), "description": str(item.get("description") or "")[:160], "breakdowns": dims[:24]})
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
        [{"role": "system", "content": _prompt("agent_planner.md")}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        AgentPlan,
        temperature=0.1,
        max_tokens=700,
    )
    return _clean_steps(plan.steps, has_knowledge, metrics=_metric_names(catalog))[:MAX_STEPS]


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


class AgentRefinement(StrictModel):
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
        except Exception:  # noqa: BLE001 - the normal answer is the fallback
            logger.exception("agent_plan_failed")  # the full error follows; the normal answer is the fallback
            return
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
        response = assemble_response(request=request, steps=steps, responses=responses, analysis=analysis, elapsed_ms=round((perf_counter() - started) * 1000, 3))
        response = self._chat.finalize_response(response)
        if frame:
            self._chat.record_turn(request, response, frame=frame)
        else:
            self._chat.record_turn(request, response)
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
