"""The agent as a loop over tools, end to end on the sample data.

Real: ChatService, the workflow (data source, compiler, execution, overall value, checks, chart), the intent checks against the
real values, the figure check on the report. Stood in: the data source (DuckDB over the sample CSVs) and the language model, which
returns the turns and the report an agent would write, reading the results it is given.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from app.ask_data.agent_mode import AskDataAgent
from app.core.models import AskDataRequest
from tests.replay_support import Replay, ScriptedModel

REGION = "delivery_shipments_region_name"
CARRIER = "delivery_shipments_carrier"
QUESTION = "Kenapa pengiriman di Kalimantan Timur sering terlambat?"


def _late(breakdown: list[str], filters: list[dict] | None = None, why: str = "") -> dict[str, Any]:
    return {"tool": "query_metric", "why": why, "query": {"metric": "late_delivery_rate", "breakdown": breakdown, "filters": filters or []}}


class AgentModel(ScriptedModel):
    """Turn 1: the rate by region and by carrier, at once. Turn 2: carriers within Kalimantan Timur (the value in lower case, as a
    model may write it) and a call with a breakdown the metric does not have. Then done. The report first quotes a figure that is
    in no result, then corrects it when told."""

    def __init__(self, *, wrong_figure_first: bool = True) -> None:
        super().__init__(analysis={QUESTION})
        self.turn_payloads: list[Any] = []
        self.reports = 0
        self.wrong_figure_first = wrong_figure_first
        self.report_payload: dict[str, Any] = {}

    async def generate_structured(self, messages, model, **kwargs):
        if model.__name__ == "AgentTurn":
            self.calls.append("AgentTurn")
            turn = sum(1 for m in messages if m["role"] == "assistant") + 1
            self.turn_payloads.append(json.loads(messages[-1]["content"]))
            if turn == 1:
                return model.model_validate({"thought": "where", "calls": [_late([REGION], why="Keterlambatan per regional"), _late([CARRIER], why="Per kurir")]})
            if turn == 2:
                return model.model_validate({"thought": "drill", "calls": [
                    _late([CARRIER], [{"dimension": REGION, "values": ["kalimantan timur"]}], why="Kurir di Kalimantan Timur"),
                    _late(["delivery_shipments_colour"], why="Per warna"),
                    _late([REGION], why="Lagi per regional"),  # already run: not run again
                ]})
            return model.model_validate({"thought": "enough", "calls": [], "done": True})
        if model.__name__ == "AgentReport":
            self.calls.append("AgentReport")
            self.reports += 1
            if self.reports == 1:
                self.report_payload = json.loads(messages[1]["content"])
            drill = next(r for r in self.report_payload["results"] if r["id"] == 3)
            top = drill["computed"]["highest"]
            figure = "99,9" if self.wrong_figure_first and self.reports == 1 else f"{top['value']:.1f}".replace(".", ",")
            return model.model_validate({
                "headline": f"Di Kalimantan Timur, {top['group']} paling sering terlambat: {figure}%.",
                "body": "### Temuan\n1. Keterlambatan terkonsentrasi di satu kurir.\n\n| Kurir | Late rate |\n|---|---|\n| x | y |",
                "follow_up_questions": ["Late delivery rate per bulan di Kalimantan Timur"],
                "show": 3,
            })
        return await super().generate_structured(messages, model, **kwargs)


@pytest.fixture()
def replay(monkeypatch):
    from app.ask_data import answer_context, value_filters

    value_filters.clear_cache()
    yield Replay(monkeypatch, AgentModel())
    answer_context._COVERAGE.clear()
    value_filters.clear_cache()


def _run(replay: Replay, question: str = QUESTION) -> tuple[Any, list[dict[str, Any]]]:
    request = AskDataRequest(session_id=replay.session_id, question=question, provider="qwen", model="m", agent_loop="tools")

    async def go():
        return [event async for event in AskDataAgent(replay.service).stream(request)]

    events = asyncio.run(go())
    return events[-1].get("response"), events


def test_the_agent_queries_looks_drills_and_writes_one_report(replay) -> None:
    response, events = _run(replay)
    assert response is not None and response.strategy == "agent" and response.status == "SUCCESS"
    model = replay.model
    assert model.calls.count("AgentTurn") == 3 and "AnalysisOutput" not in model.calls and "QueryIntent" not in model.calls
    # The tools ran governed queries with no language-model call inside: the turns, the report and its correction are all.
    first_results = {r["id"]: r for r in model.turn_payloads[1]["results"]}
    assert first_results[1]["status"] == "ok" and first_results[1]["row_count"] > 1 and "computed" in first_results[1]
    assert first_results[1]["overall_value"] is not None  # the value the regions are read against
    second = {r.get("id", r.get("see_id")): r for r in model.turn_payloads[2]["results"]}
    assert second[3]["status"] == "ok" and second[3]["overall_value_covers"].startswith("only")  # Kalimantan Timur, not national
    assert second[4]["status"] == "invalid" and "breakdown" in second[4]["problems"][0]  # told what to correct
    assert any(r.get("status") == "already_run" for r in model.turn_payloads[2]["results"])
    assert any("region_name = 'Kalimantan Timur'" in q for q in replay.executor.queries)  # the data's own spelling
    # The report: shaped by the question, its figures checked; the wrong one was sent back once and corrected.
    assert model.reports == 2 and "99,9" not in response.answer.direct_answer
    assert response.answer.executive_summary.startswith("### Temuan") and not response.answer.caveats
    assert response.data.row_count > 1 and response.chart_spec is not None  # the drill the report chose to show
    assert response.calculation.kind == "agent" and len(response.calculation.steps) == 3  # the invalid call is not a step
    labels = [e["label"] for e in events if e["type"] == "progress"]
    assert "Checking: Keterlambatan per regional" in labels and any(l.startswith("Kurir di Kalimantan Timur:") for l in labels)
    assert replay.service.history.load(replay.session_id)[-1]["session_frame"]["metric"] == "late_delivery_rate"  # a follow-up continues it
    # The checks behind the answer are shown as cards, and what they found travels with the turn.
    cards = response.agent_steps
    assert [c.title for c in cards] == ["Keterlambatan per regional", "Per kurir", "Kurir di Kalimantan Timur"]
    assert all(c.status == "ok" and c.rows and c.sql for c in cards) and cards[2].overall_value is not None
    frame = replay.service.history.load(replay.session_id)[-1]["session_frame"]
    assert [f["check"] for f in frame["agent_findings"]] == [c.title for c in cards] and frame["agent_findings"][0]["top_rows"]
    from app.ask_data.conversation import previous_turns

    turn = previous_turns(replay.service.history.load(replay.session_id))[-1]
    assert turn["kind"] == "analysis" and turn["findings"][0]["check"] == "Keterlambatan per regional"


def test_a_figure_still_not_in_the_results_is_said(monkeypatch) -> None:
    from app.ask_data import value_filters

    value_filters.clear_cache()

    class Stubborn(AgentModel):
        async def generate_structured(self, messages, model, **kwargs):
            if model.__name__ == "AgentReport":
                self.calls.append("AgentReport")
                return model.model_validate({"headline": "Rata-rata 99,9% terlambat.", "body": "", "show": None})
            return await super().generate_structured(messages, model, **kwargs)

    replay = Replay(monkeypatch, Stubborn())
    response, _ = _run(replay)
    assert any("99,9" in c for c in response.answer.caveats)


def test_plan_mode_is_unchanged_and_the_tool_loop_is_not_used(replay) -> None:
    request = AskDataRequest(session_id=replay.session_id, question=QUESTION, provider="qwen", model="m", agent_loop="plan")
    asyncio.run(AskDataAgent(replay.service).run(request))
    assert "AgentTurn" not in replay.model.calls


def test_when_no_query_answers_the_normal_pipeline_answers(monkeypatch) -> None:
    from app.ask_data import value_filters

    value_filters.clear_cache()

    class OnlyInvalid(AgentModel):
        async def generate_structured(self, messages, model, **kwargs):
            if model.__name__ == "AgentTurn":
                self.calls.append("AgentTurn")
                return model.model_validate({"calls": [_late(["nope"])]})
            return await super().generate_structured(messages, model, **kwargs)

    replay = Replay(monkeypatch, OnlyInvalid())
    response, events = _run(replay)
    assert response is None and not any(e["type"] == "done" for e in events)
    assert "AgentReport" not in replay.model.calls


def test_the_report_may_propose_actions_and_only_valid_ones_reach_the_user(monkeypatch) -> None:
    from app.ask_data import value_filters
    from tests.test_mcp_actions import ACTION

    value_filters.clear_cache()

    class Proposing(AgentModel):
        def __init__(self) -> None:
            super().__init__(wrong_figure_first=False)
            self.saw_tools = False

        async def generate_structured(self, messages, model, **kwargs):
            if model.__name__ == "AgentReport":
                self.saw_tools = "action_tools" in json.loads(messages[1]["content"])
                report = await super().generate_structured(messages, model, **kwargs)
                return report.model_copy(update={"actions": [
                    {"server_id": "ops", "tool": "create_ticket", "title": "Buat tiket", "arguments": {"title": "Kurir KT", "description": "evaluasi", "priority": "high"}},
                    {"server_id": "ops", "tool": "create_ticket", "title": "salah", "arguments": {"priority": "urgent"}},
                ]})
            return await super().generate_structured(messages, model, **kwargs)

    replay = Replay(monkeypatch, Proposing())

    async def listed():
        return [ACTION]

    replay.service.agent_actions = listed  # type: ignore[method-assign]
    response, _ = _run(replay)
    assert replay.model.saw_tools
    assert [a.title for a in response.proposed_actions] == ["Buat tiket"]  # the invalid one never reaches the user
    assert response.proposed_actions[0].arguments["priority"] == "high"


def test_a_figure_quoted_from_a_document_counts_as_found_but_a_made_up_one_does_not() -> None:
    from app.ask_data import agent_tools
    from app.core.models import AnalysisOutput, AskDataResponse, CitationRecord, QueryData, Timings

    def response(rows, citations=None, text=""):
        answer = AnalysisOutput(direct_answer=text, executive_summary="", insights=[], business_implications=[], caveats=[], data_reference="x")
        return AskDataResponse(request_id="r", session_id="s", status="SUCCESS", provider="qwen", model="m", strategy="governed", answer=answer,
                               data=QueryData(columns=["terminal", "metric_value"], rows=rows, row_count=len(rows)), chart_spec=None, timings=Timings(), citations=citations)

    data = agent_tools.Call(1, agent_tools.ToolCall(tool="query_metric", query={"metric": "late"}))
    data.response = response([{"terminal": "Sorong", "metric_value": 36.31}, {"terminal": "Wayame", "metric_value": 30.12}])
    doc = agent_tools.Call(2, agent_tools.ToolCall(tool="search_documents", search="ambang"))
    doc.response = response([], citations=[CitationRecord(document_id="d", filename="SOP.pdf", page_number=1, chunk_id="c", snippet="rute dengan jarak di atas 300 km dijadwalkan malam", score=0.9)], text="Level 2 di atas 30%.")

    class Writer:
        def __init__(self, body):
            self.body = body

        async def generate_structured(self, messages, model, **kwargs):
            return model.model_validate({"headline": "Sorong 36,3%.", "body": self.body})

    request = AskDataRequest(session_id="s", question="Apa yang harus dilakukan?", provider="qwen", model="m")
    _, bad = asyncio.run(agent_tools.write_report(Writer("Jadwalkan malam untuk rute di atas 300 km."), request=request, question=request.question, language="id", calls=[data, doc], data_coverage=None))
    assert bad == []
    _, bad = asyncio.run(agent_tools.write_report(Writer("Turunkan ke 412 LO per minggu."), request=request, question=request.question, language="id", calls=[data, doc], data_coverage=None))
    assert bad == ["412"]


def test_the_mean_of_group_rates_is_not_a_valid_comparison_point_but_the_mean_of_volumes_is() -> None:
    from app.ask_data import agent_tools
    from app.core.models import AnalysisOutput, AskDataResponse, QueryData, Timings

    def call(index: int, expression: str, rows: list[dict]) -> agent_tools.Call:
        item = agent_tools.Call(index, agent_tools.ToolCall(tool="query_metric", query={"metric": "m"}))
        answer = AnalysisOutput(direct_answer="", executive_summary="", insights=[], business_implications=[], caveats=[], data_reference="x")
        data = QueryData(columns=["group", "metric_value"], rows=rows, row_count=len(rows), governed_metric_expression=expression)
        item.response = AskDataResponse(request_id="r", session_id="s", status="SUCCESS", provider="qwen", model="m", strategy="governed", answer=answer, data=data, chart_spec=None, timings=Timings())
        return item

    rate = call(1, "COUNT(CASE WHEN late THEN 1 END) * 100.0 / COUNT(*)", [{"group": "A", "metric_value": 30.5}, {"group": "B", "metric_value": 20.1}])
    volume = call(2, "SUM(volume_kl)", [{"group": "A", "metric_value": 100.5}, {"group": "B", "metric_value": 200.7}])
    allowed = agent_tools._allowed_figures([rate, volume], "")
    from app.ask_data.answer_checks import figures_outside

    assert figures_outside(["The regional average is 25.3%."], allowed) == ["25.3"]  # the mean of two rates
    assert figures_outside(["Average volume per region is 150.6 KL."], allowed) == []  # the mean of volumes adds up
    assert figures_outside(["A is 30.5%, B is 20.1%."], allowed) == []
