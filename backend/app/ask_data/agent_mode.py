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

_OPEN_QUESTION = re.compile(
    r"\b(why|how come|root cause|what (?:is|are) (?:the )?(?:cause|reason|driver)s?|what should (?:we|i)|how (?:can|could|do|should) (?:we|i) (?:improve|reduce|fix|increase|lower|raise)"
    r"|recommend\w*|diagnos\w*|investigate|kenapa|mengapa|penyebab|apa yang (?:harus|perlu|sebaiknya)|bagaimana (?:cara )?(?:memperbaiki|meningkatkan|mengurangi|menurunkan)|rekomendasi|analisis mendalam)\b",
    re.I,
)


def is_open_question(question: str) -> bool:
    return bool(_OPEN_QUESTION.search(question or ""))


class AgentStep(StrictModel):
    kind: Literal["data", "knowledge"]
    question: str
    why: str = ""


class AgentPlan(StrictModel):
    steps: list[AgentStep]


def _prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def _humanize_catalog(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for item in catalog:
        dims = [readable_name(str(d)) for d in item.get("allowed_dimensions") or []]
        out.append({"metric": item.get("name"), "description": str(item.get("description") or "")[:160], "breakdowns": dims[:24]})
    return out


async def plan_steps(provider: Any, *, question: str, catalog: list[dict[str, Any]], has_knowledge: bool) -> list[AgentStep]:
    import json

    payload = {"question": question, "metric_catalog": _humanize_catalog(catalog), "documents_available": has_knowledge, "today": date.today().isoformat()}
    plan = await provider.generate_structured(
        [{"role": "system", "content": _prompt("agent_planner.md")}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        AgentPlan,
        temperature=0.1,
        max_tokens=700,
    )
    return _clean_steps(plan.steps, has_knowledge)[:MAX_STEPS]


def _clean_steps(raw: list[AgentStep], has_knowledge: bool, *, taken: list[AgentStep] | None = None) -> list[AgentStep]:
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
        steps.append(AgentStep(kind=step.kind, question=text, why=" ".join(step.why.split())[:160]))
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
        steps = _clean_steps(list(refined.steps), has_knowledge)[: len(remaining)]
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
    # The table and chart shown are the most informative data step: a breakdown with several rows, else the first one.
    primary = next((r for _, r in data_done if r.data.row_count > 1 and r.chart_spec), None) or next((r for _, r in data_done if r.data.row_count > 1), None) or (data_done[0][1] if data_done else None)
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
        from app.core.config import get_settings

        return bool(get_settings().agent_mode_enabled) and request.mode == "ask_data" and is_open_question(request.question)

    def _knowledge_library_ids(self) -> list[str]:
        return self._chat.ready_library_ids()

    async def stream(self, request: AskDataRequest) -> AsyncIterator[dict[str, Any]]:
        """Progress events, then {"type": "done", "response": ...}; yields nothing at all when agent mode does not apply."""
        if not self.applicable(request):
            return
        started = perf_counter()
        try:
            prepared, provider = self._chat.provider_for(request)
            catalog = self._chat.metric_catalog()
            library_ids = self._knowledge_library_ids()
            if not catalog:
                logger.warning("agent_fallback reason=no_metric_catalog")
                return
            yield {"type": "progress", "stage": "agent_plan", "label": "Planning the analysis"}
            steps = await plan_steps(provider, question=request.question, catalog=catalog, has_knowledge=bool(library_ids))
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
            yield {"type": "progress", "stage": "agent_step", "label": f"Step {index} of {len(steps)}: {step.why or step.question}", "detail": step.question}
            sub = prepared.model_copy(
                update={
                    "session_id": f"agent-{run_id}-{index}",
                    "question": step.question,
                    "mode": "rag" if step.kind == "knowledge" else "ask_data",
                    "library_ids": library_ids if step.kind == "knowledge" else None,
                }
            )
            try:
                responses.append(await self._chat.run(sub))
            except Exception:  # noqa: BLE001 - one failing step must not stop the others
                logger.exception("agent_step_failed step=%s", index)
                responses.append(None)
            first = responses[0]
            if index == 1 and len(steps) > 2 and first is not None and first.status == "SUCCESS" and step.kind == "data":
                steps = [step, *await refine_steps(provider, question=request.question, catalog=catalog, has_knowledge=bool(library_ids), done=[_step_result(1, step, first)], remaining=steps[1:])]
        if not any(r is not None and r.status == "SUCCESS" and s.kind == "data" for s, r in zip(steps, responses)):
            logger.warning("agent_fallback reason=no_step_answered statuses=%s", [getattr(r, "status", None) for r in responses])
            return  # nothing to report: let the normal pipeline answer
        yield {"type": "progress", "stage": "agent_report", "label": "Writing the report"}
        try:
            import json

            _, provider = self._chat.provider_for(request)  # each step cleared the model context
            results = [_step_result(i + 1, s, r) for i, (s, r) in enumerate(zip(steps, responses))]
            analysis = await provider.generate_structured(
                [
                    {"role": "system", "content": _prompt("agent_report.md")},
                    {"role": "user", "content": json.dumps({"question": request.question, "language": detect_language(request.question), "steps": results}, ensure_ascii=False, default=str)},
                ],
                AnalysisOutput,
                temperature=0.2,
                max_tokens=1800,
            )
        except Exception:  # noqa: BLE001
            logger.exception("agent_report_failed")
            return
        response = assemble_response(request=request, steps=steps, responses=responses, analysis=analysis, elapsed_ms=round((perf_counter() - started) * 1000, 3))
        response = self._chat.finalize_response(response)
        self._chat.record_turn(request, response)
        yield {"type": "done", "response": response}

    async def run(self, request: AskDataRequest) -> AskDataResponse | None:
        final = None
        async for event in self.stream(request):
            if event.get("type") == "done":
                final = event["response"]
        return final
