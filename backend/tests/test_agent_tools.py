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
    comparison = first_results[1]["computed"]
    assert comparison["above_overall"]["count"] + comparison["below_overall"]["count"] == comparison["above_overall"]["of"]
    assert set(comparison["above_overall"]["groups"] + comparison["below_overall"]["groups"]) == {
        row[REGION] for row in first_results[1]["rows"]
    }
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


def test_compare_joins_two_governed_periods_and_works_out_the_change(monkeypatch) -> None:
    from app.ask_data import value_filters

    value_filters.clear_cache()

    class Comparing(AgentModel):
        def __init__(self, periods) -> None:
            super().__init__(wrong_figure_first=False)
            self.periods = periods
            self.seen: dict = {}

        async def generate_structured(self, messages, model, **kwargs):
            if model.__name__ == "AgentTurn":
                self.calls.append("AgentTurn")
                if sum(1 for m in messages if m["role"] == "assistant") == 0:
                    a, b, c = self.periods
                    return model.model_validate({"calls": [{"tool": "compare", "why": "Kurir: paruh pertama vs kedua", "compare": {
                        "mode": "periods", "metric": "late_delivery_rate", "breakdown": [CARRIER],
                        "period_a_start": a, "period_a_end": b, "period_b_start": b, "period_b_end": c}}]})
                self.seen = json.loads(messages[-1]["content"])
                return model.model_validate({"done": True})
            if model.__name__ == "AgentReport":
                self.calls.append("AgentReport")
                return model.model_validate({"headline": "Perbandingan kurir.", "body": "", "show": 1})
            return await super().generate_structured(messages, model, **kwargs)

    probe = Replay(monkeypatch, AgentModel())
    first, last = probe.executor.con.execute("SELECT MIN(CAST(ship_date AS DATE)), MAX(CAST(ship_date AS DATE)) FROM delivery_shipments").fetchone()
    middle = first + (last - first) / 2
    periods = (first.isoformat(), middle.isoformat(), (last + __import__("datetime").timedelta(days=1)).isoformat())
    replay = Replay(monkeypatch, Comparing(periods))
    response, _ = _run(replay)
    card = response.agent_steps[0]
    assert card.tool == "compare" and card.status == "ok" and {"value_a", "value_b", "change", "change_pct"} <= set(card.columns)
    row = card.rows[0]
    assert abs(row["change"] - (row["value_b"] - row["value_a"])) < 1e-3  # worked out by code (rounded), not the model
    assert card.sql and card.sql.count("SELECT") >= 2  # two governed queries, one per period
    assert response.data.row_count == len({r[CARRIER] for r in card.rows}) or response.data.row_count >= 2


def test_the_agent_asks_back_when_only_the_user_can_choose_and_runs_no_query(monkeypatch) -> None:
    from app.ask_data import value_filters

    value_filters.clear_cache()

    class Asking(AgentModel):
        async def generate_structured(self, messages, model, **kwargs):
            if model.__name__ == "AgentTurn":
                self.calls.append("AgentTurn")
                return model.model_validate({"clarify_question": "Dibandingkan dengan periode mana?", "clarify_options": [
                    "Bandingkan keterlambatan Juni 2026 dengan Mei 2026", "Bandingkan keterlambatan 2026 dengan 2025"]})
            return await super().generate_structured(messages, model, **kwargs)

    replay = Replay(monkeypatch, Asking())
    response, _ = _run(replay)
    assert response.strategy == "agent" and response.answer.direct_answer == "Dibandingkan dengan periode mana?"
    assert response.answer.follow_up_questions == ["Bandingkan keterlambatan Juni 2026 dengan Mei 2026", "Bandingkan keterlambatan 2026 dengan 2025"]
    assert not [q for q in replay.executor.queries if "metric_value" in q] and "AgentReport" not in replay.model.calls  # no metric was queried


def test_with_agent_all_a_plain_data_question_is_answered_by_the_agent_and_without_it_is_not(monkeypatch) -> None:
    from app.ask_data import value_filters

    value_filters.clear_cache()
    question = "Late delivery rate per carrier"

    class Narrow(AgentModel):
        async def generate_structured(self, messages, model, **kwargs):
            if model.__name__ == "AgentTurn":
                self.calls.append("AgentTurn")
                if sum(1 for m in messages if m["role"] == "assistant") == 0:
                    return model.model_validate({"calls": [_late([CARRIER], why="Per kurir")]})
                return model.model_validate({"done": True})
            if model.__name__ == "AgentReport":
                self.calls.append("AgentReport")
                return model.model_validate({"headline": "NusaCargo paling sering terlambat.", "body": "", "show": 1})
            return await super().generate_structured(messages, model, **kwargs)

    replay = Replay(monkeypatch, Narrow())
    request = AskDataRequest(session_id=replay.session_id, question=question, provider="qwen", model="m", agent_all=True)
    response = asyncio.run(AskDataAgent(replay.service).run(request))
    assert response is not None and response.strategy == "agent" and response.data.governed_metric == "late_delivery_rate"
    assert replay.model.calls.count("AgentTurn") == 2  # one query, then done: a narrow question stays short
    off = AskDataRequest(session_id="other", question=question, provider="qwen", model="m", agent_all=False)
    assert asyncio.run(AskDataAgent(replay.service).run(off)) is None  # the governed pipeline answers it


def test_the_chat_gets_the_summary_and_the_panel_gets_the_full_analysis(monkeypatch) -> None:
    from app.ask_data import value_filters

    value_filters.clear_cache()
    question = "Late delivery rate per carrier"

    class TwoDepths(AgentModel):
        async def generate_structured(self, messages, model, **kwargs):
            if model.__name__ == "AgentTurn":
                if sum(1 for m in messages if m["role"] == "assistant") == 0:
                    return model.model_validate({"calls": [_late([CARRIER], why="Per kurir")]})
                return model.model_validate({"done": True})
            if model.__name__ == "AgentReport":
                return model.model_validate(
                    {
                        "headline": "NusaCargo paling sering terlambat.",
                        "summary": "Keterlambatan terpusat di satu kurir.",
                        "body": "### Di mana terpusat\n\nSatu kurir menanggung sebagian besar keterlambatan.",
                        "show": 1,
                    }
                )
            return await super().generate_structured(messages, model, **kwargs)

    replay = Replay(monkeypatch, TwoDepths())
    request = AskDataRequest(session_id=replay.session_id, question=question, provider="qwen", model="m", agent_all=True)
    response = asyncio.run(AskDataAgent(replay.service).run(request))
    assert response is not None and response.strategy == "agent"
    assert response.answer.executive_summary == "Keterlambatan terpusat di satu kurir."  # the chat
    assert response.analysis_report.startswith("### Di mana terpusat")  # the panel, not a copy of the chat


def test_a_report_without_a_summary_keeps_its_body_in_the_chat() -> None:
    from app.ask_data.agent_tools import AgentReport, report_to_analysis

    old = report_to_analysis(AgentReport(headline="H", body="B"), unverified=[], language="id", data_reference="")
    assert old.executive_summary == "B"
    new = report_to_analysis(AgentReport(headline="H", summary="S", body="B"), unverified=[], language="id", data_reference="")
    assert new.executive_summary == "S"


def test_the_recommended_actions_reach_the_response_as_a_table_and_their_figures_are_checked(monkeypatch) -> None:
    from app.ask_data import value_filters

    value_filters.clear_cache()

    class Advising(AgentModel):
        async def generate_structured(self, messages, model, **kwargs):
            if model.__name__ == "AgentTurn":
                if sum(1 for m in messages if m["role"] == "assistant") == 0:
                    return model.model_validate({"calls": [_late([CARRIER], why="Per kurir")]})
                return model.model_validate({"done": True})
            if model.__name__ == "AgentReport":
                return model.model_validate(
                    {
                        "headline": "NusaCargo paling sering terlambat.",
                        "summary": "Tindakan pertama menyasar satu kurir.",
                        "body": "### Rekomendasi Tindakan\n\nUrutan mengikuti dampak.",
                        "recommendations": [
                            {"priority": "Tinggi", "action": "Buat tiket tindak lanjut", "basis": "NusaCargo di atas rata-rata", "owner": "Regional Distribution Manager", "timeframe": "24 jam", "source": "SOP, hal. 1"},
                            {"action": "   "},
                        ],
                        "show": 1,
                    }
                )
            return await super().generate_structured(messages, model, **kwargs)

    replay = Replay(monkeypatch, Advising())
    request = AskDataRequest(session_id=replay.session_id, question="Late delivery rate per carrier, apa yang harus dilakukan?", provider="qwen", model="m", agent_all=True)
    response = asyncio.run(AskDataAgent(replay.service).run(request))
    assert response is not None
    assert [r.action for r in response.recommendations] == ["Buat tiket tindak lanjut"]  # an empty row is dropped
    assert response.recommendations[0].owner == "Regional Distribution Manager" and response.recommendations[0].source == "SOP, hal. 1"


def test_the_agent_report_sections_become_a_laid_out_body_with_formal_headings(monkeypatch) -> None:
    from app.ask_data import value_filters

    value_filters.clear_cache()

    class Sectioned(AgentModel):
        async def generate_structured(self, messages, model, **kwargs):
            if model.__name__ == "AgentTurn":
                if sum(1 for m in messages if m["role"] == "assistant") == 0:
                    return model.model_validate({"calls": [_late([CARRIER], why="Per kurir")]})
                return model.model_validate({"done": True})
            if model.__name__ == "AgentReport":
                return model.model_validate(
                    {
                        "headline": "NusaCargo paling sering terlambat.",
                        "summary": "Keterlambatan terpusat di satu kurir.",
                        "sections": [
                            {"kind": "detail", "paragraphs": ["Satu kurir menanggung sebagian besar keterlambatan."]},
                            {"kind": "drivers", "bullets": ["Kemungkinan terkait kapasitas armada, belum terbukti."]},
                        ],
                        "show": 1,
                    }
                )
            return await super().generate_structured(messages, model, **kwargs)

    replay = Replay(monkeypatch, Sectioned())
    request = AskDataRequest(session_id=replay.session_id, question="Late delivery rate per carrier", provider="qwen", model="m", agent_all=True)
    response = asyncio.run(AskDataAgent(replay.service).run(request))
    assert response is not None
    # the question is in English, so the headings are too
    assert response.analysis_report.startswith("### Detailed Explanation\n\nSatu kurir menanggung")
    assert "### Possible Drivers\n\n- Kemungkinan terkait kapasitas armada, belum terbukti." in response.analysis_report


def _item(index: int, call_dict: dict[str, Any]):
    from app.ask_data.agent_tools import Call, ToolCall

    return Call(index, ToolCall.model_validate(call_dict))


CATALOG = {"metrics": [{"name": "late_rate", "label": "Late Rate", "breakdowns": ["regional", "provinsi"]}, {"name": "volume", "label": "Volume", "breakdowns": ["terminal"]}]}


def test_a_filtered_call_gets_the_same_call_over_every_group_of_the_filtered_dimension() -> None:
    from app.ask_data.agent_tools import CONTEXT_CALLS_PER_RUN, _context_calls

    named = {"tool": "query_metric", "why": "Per provinsi", "query": {"metric": "late_rate", "breakdown": ["provinsi"], "filters": [{"dimension": "regional", "values": ["A", "B"]}], "by_month": True, "limit": 5}}
    fresh = [_item(1, named)]
    added = _context_calls(fresh, CATALOG, {}, "id", 0)
    assert len(added) == 1 and added[0].context
    context = added[0].call.query
    assert context.breakdown == ["regional"] and context.filters == [] and context.by_month is False and context.limit is None  # all groups, whole period
    assert added[0].call.why == "Konteks semua regional: Late Rate"

    # a comparison filtered to one place gets the comparison over every place, with its own periods
    compare = {"tool": "compare", "compare": {"mode": "periods", "metric": "volume", "breakdown": ["terminal"], "filters": [{"dimension": "terminal", "values": ["Kertapati"]}], "period_a_start": "2025-07-01", "period_a_end": "2025-08-01", "period_b_start": "2025-08-01", "period_b_end": "2025-09-01"}}
    context = _context_calls([_item(2, compare)], CATALOG, {}, "en", 0)[0].call
    assert context.compare.filters == [] and context.compare.breakdown == ["terminal"] and context.compare.period_b_start == "2025-08-01"
    assert context.why == "Context, every terminal: Volume"

    # nothing is added for an unfiltered call, a dimension the metric cannot be broken down by, a repeat, or past the limit per run
    assert _context_calls([_item(1, {"tool": "query_metric", "query": {"metric": "late_rate", "breakdown": ["regional"]}})], CATALOG, {}, "id", 0) == []
    assert _context_calls([_item(1, {"tool": "query_metric", "query": {"metric": "late_rate", "filters": [{"dimension": "colour", "values": ["red"]}]}})], CATALOG, {}, "id", 0) == []
    seen: dict[str, int] = {}
    assert len(_context_calls(fresh, CATALOG, seen, "id", 0)) == 1 and _context_calls(fresh, CATALOG, seen, "id", 0) == []
    many = [_item(n, {"tool": "query_metric", "query": {"metric": "late_rate", "breakdown": ["provinsi"], "filters": [{"dimension": "regional", "values": [f"R{n}"]}], "period_start": f"2025-0{n}-01"}}) for n in range(1, 8)]
    assert len(_context_calls(many[:3], CATALOG, {}, "id", 0)) <= CONTEXT_CALLS_PER_RUN


def _compare_item(rows: list[dict[str, Any]]):
    from types import SimpleNamespace

    item = _item(1, {"tool": "compare", "compare": {"mode": "periods", "metric": "volume", "breakdown": ["terminal"]}})
    item.response = SimpleNamespace(status="SUCCESS", data=SimpleNamespace(rows=rows))
    return item


def test_a_report_that_misses_where_the_amount_moved_is_given_the_facts_to_name_it_with() -> None:
    from app.ask_data.agent_tools import _shift_hint

    rows = [
        {"terminal": "Panjang", "value_a": 6816, "value_b": 11944, "change": 5128},
        {"terminal": "Kertapati", "value_a": 6168, "value_b": 2056, "change": -4112},
        {"terminal": "Wayame", "value_a": 900, "value_b": 905, "change": 5},
    ]
    hint = _shift_hint([_compare_item(rows)], "Volume Kertapati turun karena jumlah LO turun.")
    assert hint is not None and "Panjang rose by 5128 (from 6816 to 11944)" in hint and "Kertapati fell by 4112" in hint
    assert "leave it out" in hint  # whether it bears on the question stays the model's call
    assert _shift_hint([_compare_item(rows)], "Volume Kertapati pindah ke Panjang, yang naik 5.128 KL.") is None  # already named
    small = [{"terminal": "A", "change": 40}, {"terminal": "B", "change": -4112}]
    assert _shift_hint([_compare_item(small)], "turun") is None  # a rise of 40 against a fall of 4,112 is not where it went
    assert _shift_hint([_compare_item([{"terminal": "A", "change": -5}, {"terminal": "B", "change": -9}])], "x") is None  # nothing rose
    assert _shift_hint([], "x") is None


def test_the_agent_runs_the_context_call_beside_a_filtered_one_and_the_report_sees_it(monkeypatch) -> None:
    from app.ask_data import value_filters

    value_filters.clear_cache()
    seen: dict[str, Any] = {}

    class Filtering(AgentModel):
        """Turn 1: carriers over everything. Turn 2: carriers within one region only, which hides every other region."""

        async def generate_structured(self, messages, model, **kwargs):
            if model.__name__ == "AgentTurn":
                self.calls.append("AgentTurn")
                turn = sum(1 for m in messages if m["role"] == "assistant") + 1
                if turn == 1:
                    return model.model_validate({"calls": [_late([CARRIER], why="Per kurir")]})
                if turn == 2:
                    return model.model_validate({"calls": [_late([CARRIER], [{"dimension": REGION, "values": ["kalimantan timur"]}], why="Kurir di Kalimantan Timur")]})
                return model.model_validate({"done": True})
            if model.__name__ == "AgentReport":
                self.calls.append("AgentReport")
                seen["results"] = json.loads(messages[1]["content"])["results"]
                return model.model_validate({"headline": "Di Kalimantan Timur satu kurir paling sering terlambat.", "summary": "Terpusat.", "show": 2})
            return await super().generate_structured(messages, model, **kwargs)

    replay = Replay(monkeypatch, Filtering())
    response, _ = _run(replay)
    titles = [step.title for step in response.agent_steps]
    context = [r for r in seen["results"] if r.get("context")]
    assert len(context) == 1 and context[0]["query"]["breakdown"] == [REGION] and "filters" not in context[0]["query"]  # every region, no filter
    assert context[0]["status"] == "ok" and context[0]["overall_value"] > 0  # with the overall value of everything
    assert any(title.startswith("Konteks semua") for title in titles)
