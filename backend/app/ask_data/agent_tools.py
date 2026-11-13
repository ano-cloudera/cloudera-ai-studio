"""The agent as a loop over tools, the way Genie's research agent or an analyst works: query, look at the result, decide what to
check next, and write one report when the results answer the question.

Each turn the language model returns what it learned so far and up to four tool calls, which run at the same time:

* query_metric: a governed query from a structured intent (metric, breakdown, by month, filters, period, order, limit), named
  only from the published model. Code checks it against the catalog and the real values, compiles the SQL from the metric's own
  formula, checks the SQL and runs it (ChatService.query_metric). No language-model call happens inside the tool, so a call
  costs one warehouse query, not a whole question. An invalid call comes back with what was wrong, and the model corrects it.
* search_documents: a question to the document libraries (SOP, policies), answered with citations.

The loop is bounded (turns, calls and time), never repeats a call, and ends with a report the model writes in the form the
question needs (markdown: a sentence, or sections, numbered recommendations, a small table). Every figure in the report is
checked against the results; a figure that is not there is sent back once to be corrected, and still unverified it is said.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from pathlib import Path
from time import perf_counter
from typing import Any, AsyncIterator, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ask_data.understanding import IntentFilter, QueryIntent
from app.core.models import AnalysisOutput, AskDataRequest, AskDataResponse

logger = logging.getLogger(__name__)

PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"
MAX_TURNS = 4
MAX_CALLS_PER_TURN = 4
MAX_CALLS = 10
EXPLORE_SECONDS = 75.0  # after this no new turn starts; the report is written from what was found
MAX_ROWS_SHOWN = 30


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


class MetricQuery(_Lenient):
    metric: str = Field(default="", description="The `name` of one metric from the catalog.")
    breakdown: list[str] = Field(default_factory=list, description="Dimension `key`s from the metric's `breakdowns`.")
    by_month: bool = False
    filters: list[IntentFilter] = Field(default_factory=list)
    period_start: str | None = None
    period_end: str | None = None
    sort: Literal["desc", "asc"] = "desc"
    limit: int | None = None


class ToolCall(_Lenient):
    tool: Literal["query_metric", "search_documents"]
    why: str = Field(default="", description="A short phrase in the question's language, shown to the user while the call runs.")
    query: MetricQuery | None = None
    search: str = ""


class AgentTurn(_Lenient):
    thought: str = ""
    calls: list[ToolCall] = Field(default_factory=list)
    done: bool = False


class ProposedAction(_Lenient):
    server_id: str = ""
    tool: str
    title: str = Field(default="", description="What the action does, in the user's language, shown on the approval button.")
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentReport(_Lenient):
    headline: str
    body: str = ""
    follow_up_questions: list[str] = Field(default_factory=list)
    show: int | None = None
    actions: list[ProposedAction] = Field(default_factory=list)


class Call:
    """One executed tool call: what was asked, what came back, and what the model is shown of it."""

    def __init__(self, index: int, call: ToolCall) -> None:
        self.index = index
        self.call = call
        self.response: AskDataResponse | None = None
        self.frame: dict[str, Any] | None = None
        self.problems: list[str] = []
        self.seconds = 0.0

    @property
    def ok(self) -> bool:
        return self.response is not None and self.response.status == "SUCCESS"

    @property
    def is_data(self) -> bool:
        return self.call.tool == "query_metric"

    def label(self) -> str:
        if self.call.why.strip():
            return " ".join(self.call.why.split())[:120]
        if self.call.query is not None:
            return self.call.query.metric
        return self.call.search[:120]


def _prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def _signature(call: ToolCall) -> str:
    if call.tool == "query_metric" and call.query is not None:
        q = call.query.model_dump()
        q["breakdown"] = sorted(q["breakdown"])
        q["filters"] = sorted((f["dimension"], sorted(f["values"])) for f in q["filters"])
        return "q:" + json.dumps(q, sort_keys=True, default=str)
    return "s:" + " ".join(call.search.casefold().split())


def _numbers(value: Any) -> list[float]:
    """Every number in a nested value (the `computed` figures), for the figure check."""
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, dict):
        return [n for v in value.values() for n in _numbers(v)]
    if isinstance(value, list):
        return [n for v in value for n in _numbers(v)]
    return []


def observation(item: Call) -> dict[str, Any]:
    """What the model is shown of a call: the rows and the figures worked out by code, or what was wrong."""
    base: dict[str, Any] = {"id": item.index, "tool": item.call.tool, "why": item.label()}
    if item.call.tool == "query_metric" and item.call.query is not None:
        base["query"] = item.call.query.model_dump(exclude_defaults=True)
    if item.problems:
        return {**base, "status": "invalid", "problems": item.problems}
    response = item.response
    if response is None:
        return {**base, "status": "failed"}
    if response.status == "NO_DATA":
        return {**base, "status": "no_data", "message": response.answer.direct_answer[:300]}
    if response.status != "SUCCESS":
        return {**base, "status": "failed", "message": response.answer.direct_answer[:300]}
    if not item.is_data:
        return {
            **base,
            "status": "ok",
            "answer": response.answer.direct_answer[:1200],
            "sources": [{"file": c.filename, "page": c.page_number, "snippet": c.snippet[:300]} for c in (response.citations or [])[:4]],
        }
    from app.ask_data.answer_checks import computed_figures, is_additive

    data = response.data
    rows = list(data.rows[:MAX_ROWS_SHOWN])
    out: dict[str, Any] = {
        **base,
        "status": "ok",
        "metric": data.governed_metric_display_name or data.governed_metric,
        "unit": data.unit_format,
        "column_labels": dict(data.column_labels or {}),
        "rows": rows,
        "row_count": data.row_count,
    }
    if data.row_count > len(rows):
        out["rows_shown"] = len(rows)
    computed = computed_figures(rows, data.overall_value, additive=is_additive({"expression": data.governed_metric_expression or ""}))
    if computed:
        out["computed"] = computed
    if data.overall_value is not None:
        out["overall_value"] = data.overall_value
        filters = list(response.calculation.filters) if response.calculation and response.calculation.filters else []
        if filters:
            out["overall_value_covers"] = "only " + "; ".join(filters) + " as a whole, not the national or company-wide figure"
    caveats = [c for c in response.answer.caveats if c][:3]
    if caveats:
        out["caveats"] = caveats
    return out


def _figure_rows_and_extras(calls: list[Call]) -> tuple[list[dict[str, Any]], list[float]]:
    rows: list[dict[str, Any]] = []
    extras: list[float] = []
    for item in calls:
        if not (item.ok and item.is_data and item.response is not None):
            continue
        shown = observation(item)
        rows.extend(shown.get("rows") or [])
        if shown.get("overall_value") is not None:
            extras.extend(_numbers(shown["overall_value"]))
        extras.extend(_numbers(shown.get("computed") or {}))
    return rows, extras


async def _run_call(chat: Any, request: AskDataRequest, item: Call, *, library_ids: list[str], language: str, session_prefix: str) -> Call:
    began = perf_counter()
    call = item.call
    try:
        if call.tool == "query_metric":
            if call.query is None or not call.query.metric:
                item.problems = ["query_metric needs a `query` with a `metric` from the catalog"]
            else:
                intent = QueryIntent(**call.query.model_dump(), language="id" if language == "id" else "en")
                item.response, item.frame, item.problems = await chat.query_metric(request, intent, label=item.label())
        elif not library_ids:
            item.problems = ["no documents are available"]
        else:
            sub = request.model_copy(
                update={"session_id": f"{session_prefix}-{item.index}", "question": call.search or item.label(), "mode": "rag", "library_ids": library_ids}
            )
            item.response = await chat.run(sub)
    except Exception:  # noqa: BLE001 - one failing call never stops the others
        logger.exception("agent_tool_failed id=%s tool=%s", item.index, call.tool)
    item.seconds = perf_counter() - began
    logger.info(
        "agent_tool id=%s tool=%s status=%s rows=%s problems=%s seconds=%.1f why=%r",
        item.index, call.tool, getattr(item.response, "status", None), getattr(getattr(item.response, "data", None), "row_count", None),
        item.problems[:2], item.seconds, item.label(),
    )
    return item


def _labels() -> dict[str, str]:
    """The fixed words of the progress lines are the app's own, so they are in the app's language (English); the model's own
    phrases (its reasoning, what each check is for) follow the language of the question."""
    return {"think": "Analysing", "run": "Checking: {what}", "done": "{what}: {result} ({s} s)", "rows": "{n} rows", "invalid": "being corrected", "none": "no data", "failed": "failed", "report": "Writing the answer"}


def _result_word(item: Call, labels: dict[str, str]) -> str:
    if item.problems:
        return labels["invalid"]
    if item.response is None or item.response.status not in ("SUCCESS", "NO_DATA"):
        return labels["failed"]
    if item.response.status == "NO_DATA":
        return labels["none"]
    if item.is_data:
        return labels["rows"].format(n=item.response.data.row_count)
    return labels["rows"].format(n=len(item.response.citations or []))


async def explore(
    chat: Any,
    provider: Any,
    request: AskDataRequest,
    *,
    question: str,
    language: str,
    catalog: dict[str, Any],
    library_ids: list[str],
    conversation: list[dict[str, Any]] | None,
    data_coverage: str | None,
    session_prefix: str,
    calls: list[Call],
) -> AsyncIterator[dict[str, Any]]:
    """The tool loop. Progress events are yielded; the executed calls are appended to `calls`."""
    labels = _labels()
    payload: dict[str, Any] = {
        "question": question,
        "language": language,
        "today": date.today().isoformat(),
        "catalog": catalog,
        "documents_available": bool(library_ids),
    }
    if question != request.question:
        payload["question_as_asked"] = request.question
    if conversation:
        payload["conversation"] = conversation
    if data_coverage:
        payload["data_coverage"] = data_coverage
    messages: list[dict[str, str]] = [
        {"role": "system", "content": _prompt("agent_tools.md")},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
    ]
    started = perf_counter()
    seen: dict[str, int] = {}
    for turn_number in range(1, MAX_TURNS + 1):
        yield {"type": "progress", "stage": "agent_plan", "label": labels["think"]}
        try:
            turn = await provider.generate_structured(messages, AgentTurn, temperature=0.1, max_tokens=1500)
        except Exception:  # noqa: BLE001 - the report is written from what was found so far
            logger.exception("agent_turn_failed turn=%s", turn_number)
            return
        logger.info("agent_turn turn=%s thought=%r calls=%s done=%s", turn_number, turn.thought[:300], len(turn.calls), turn.done)
        if turn.thought.strip() and turn.calls:
            # What the agent concluded and checks next, shown as it works (the way Genie shows its reasoning).
            yield {"type": "progress", "stage": "agent_plan", "label": " ".join(turn.thought.split())[:240]}
        fresh: list[Call] = []
        repeated: list[dict[str, Any]] = []
        for call in turn.calls[:MAX_CALLS_PER_TURN]:
            if len(calls) + len(fresh) >= MAX_CALLS:
                break
            signature = _signature(call)
            if signature in seen:
                repeated.append({"tool": call.tool, "status": "already_run", "see_id": seen[signature]})
                continue
            item = Call(len(calls) + len(fresh) + 1, call)
            seen[signature] = item.index
            fresh.append(item)
        if not fresh:
            return  # done, or only repeats: the results so far are the answer
        for item in fresh:
            yield {"type": "progress", "stage": "agent_step", "label": labels["run"].format(what=item.label())}
        pending = [
            asyncio.create_task(_run_call(chat, request, item, library_ids=library_ids, language=language, session_prefix=session_prefix))
            for item in fresh
        ]
        try:
            for finished in asyncio.as_completed(pending):
                item = await finished
                yield {"type": "progress", "stage": "agent_step", "label": labels["done"].format(what=item.label(), result=_result_word(item, labels), s=round(item.seconds))}
        finally:
            for task in pending:
                task.cancel()  # the client went away
        calls.extend(fresh)
        for item in fresh:
            if item.problems:
                seen.pop(_signature(item.call), None)  # a corrected call may look the same in a field that was fine
        left_calls = MAX_CALLS - len(calls)
        elapsed = perf_counter() - started
        if turn.done or left_calls <= 0 or elapsed >= EXPLORE_SECONDS or turn_number == MAX_TURNS:
            return
        results = {
            "results": [observation(item) for item in fresh] + repeated,
            "remaining_calls": left_calls,
            "remaining_turns": MAX_TURNS - turn_number,
        }
        messages += [
            {"role": "assistant", "content": turn.model_dump_json()},
            {"role": "user", "content": json.dumps(results, ensure_ascii=False, default=str)},
        ]


async def write_report(
    provider: Any,
    *,
    request: AskDataRequest,
    question: str,
    language: str,
    calls: list[Call],
    data_coverage: str | None,
    action_tools: list[dict[str, Any]] | None = None,
) -> tuple[AgentReport, list[str]]:
    """The report from every result, and the figures in it that could not be found in the results (after one correction)."""
    from app.ask_data.answer_checks import unverified_figures

    payload: dict[str, Any] = {
        "question": request.question,
        "language": language,
        "results": [observation(item) for item in calls if not item.problems],
    }
    if question != request.question:
        payload["question_in_full"] = question
    if data_coverage:
        payload["data_coverage"] = data_coverage
    if action_tools:
        # Actions the user can approve (MCP tools that change something); proposed only when the question asks what to do.
        payload["action_tools"] = [
            {"server_id": a["server_id"], "tool": a["tool"], "description": a["description"], "input_schema": a["input_schema"]} for a in action_tools
        ]
    messages: list[dict[str, str]] = [
        {"role": "system", "content": _prompt("agent_tool_report.md")},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
    ]
    report = await provider.generate_structured(messages, AgentReport, temperature=0.2, max_tokens=2200)
    rows, extras = _figure_rows_and_extras(calls)
    # A figure quoted from a document (a threshold in the SOP) is as good as one from a query.
    documents = " ".join(
        " ".join([item.response.answer.direct_answer, *(c.snippet for c in (item.response.citations or []))])
        for item in calls
        if item.ok and not item.is_data and item.response is not None
    )
    question = f"{question} {documents}".strip()
    bad = unverified_figures([report.headline, report.body], rows, question, extras)
    if bad:
        logger.info("agent_report_figures_unverified figures=%s", bad)
        messages += [
            {"role": "assistant", "content": report.model_dump_json()},
            {
                "role": "user",
                "content": "These figures are not in the results and cannot be derived from them: "
                + ", ".join(bad)
                + ". Rewrite the report quoting only figures from the results (rows, overall_value, computed), or leave those figures out.",
            },
        ]
        try:
            report = await provider.generate_structured(messages, AgentReport, temperature=0.1, max_tokens=2200)
            bad = unverified_figures([report.headline, report.body], rows, question, extras)
        except Exception:  # noqa: BLE001 - the first report stands, with its figures said to be unverified
            logger.warning("agent_report_repair_failed")
    return report, bad


def report_to_analysis(report: AgentReport, *, unverified: list[str], language: str, data_reference: str) -> AnalysisOutput:
    warnings = [
        (
            f"Angka {token} pada jawaban tidak ada di hasil query dan tidak dapat diturunkan darinya, jadi gunakan dengan hati-hati."
            if language == "id"
            else f"The figure {token} in the answer is not in the query results and could not be derived from them, so treat it with care."
        )
        for token in unverified
    ]
    return AnalysisOutput(
        direct_answer=report.headline.strip(),
        executive_summary=report.body.strip(),
        insights=[],
        business_implications=[],
        caveats=warnings,
        data_reference=data_reference or "",
        follow_up_questions=report.follow_up_questions,
    )
