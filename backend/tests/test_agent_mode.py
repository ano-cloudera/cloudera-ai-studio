from __future__ import annotations

import asyncio
from typing import Any

from app.ask_data.agent_mode import AgentPlan, AgentRefinement, AgentStep, AskDataAgent, is_open_question, plan_steps
from app.core.models import (
    AnalysisOutput,
    AskDataRequest,
    AskDataResponse,
    CalculationNote,
    ChartSpec,
    CitationRecord,
    LlmUsage,
    QueryData,
    Timings,
)

CATALOG = [{"name": "late_delivery_rate", "description": "Late delivery rate", "allowed_dimensions": ["delivery_shipments_carrier", "delivery_shipments_region_name"]}]


def _analysis(text: str = "ok") -> AnalysisOutput:
    return AnalysisOutput(direct_answer=text, executive_summary="First ... Then ...", insights=["a (step 1)"], business_implications=["b"], caveats=[], data_reference="delivery_shipments", chart_spec=None)


def _response(question: str, *, status="SUCCESS", rows=None, citations=None, note=None) -> AskDataResponse:
    rows = rows if rows is not None else [{"carrier": "NusaCargo", "metric_value": 32.2}, {"carrier": "KilatKirim", "metric_value": 14.0}]
    return AskDataResponse(
        request_id="r", session_id="s", status=status, provider="gemini", model="m", strategy="rag" if citations else "governed",
        answer=_analysis(f"answer to {question}"), data=QueryData(columns=list(rows[0]) if rows else [], rows=rows, row_count=len(rows), governed_metric="late_delivery_rate"),
        chart_spec=ChartSpec(type="bar", x="carrier", y="metric_value", title="t") if rows and len(rows) > 1 else None, timings=Timings(),
        usage=LlmUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15, llm_calls=1), governed_sql="SELECT 1", citations=citations, calculation=note,
    )


class Provider:
    def __init__(self, steps: list[AgentStep], refined: list[AgentStep] | None = None) -> None:
        self.steps = steps
        self.refined = refined
        self.calls: list[str] = []

    async def generate_structured(self, messages, model, **_):
        self.calls.append(model.__name__)
        if model is AgentRefinement:
            if self.refined is None:
                raise RuntimeError("no refinement")
            return AgentRefinement(steps=self.refined)
        return AgentPlan(steps=self.steps) if model is AgentPlan else _analysis("Kalimantan Timur is late mostly through NusaCargo.")


class Chat:
    def __init__(self, provider: Provider, *, libraries: list[str] | None = None, fail_data: bool = False) -> None:
        self.provider, self.libraries, self.fail_data = provider, libraries or [], fail_data
        self.asked: list[tuple[str, str]] = []
        self.sources: list = []
        self.recorded: list[AskDataResponse] = []

    def provider_for(self, request):
        return request, self.provider

    def metric_catalog(self):
        return CATALOG

    def ready_library_ids(self):
        return self.libraries

    async def run(self, request):
        self.asked.append((request.mode, request.question))
        self.sources.append(request.context_sources)
        if request.mode == "rag":
            return _response(request.question, citations=[CitationRecord(document_id="d", filename="Delivery_Returns_Policy.pdf", page_number=2, chunk_id="c", snippet="above 15 percent", score=0.9)], rows=[])
        if self.fail_data:
            return _response(request.question, status="ERROR", rows=[])
        note = CalculationNote(kind="governed", summary="Late rate · by carrier", source=["delivery_shipments"])
        return _response(request.question, note=note)

    def finalize_response(self, response):
        return response

    def record_turn(self, request, response, **_):
        self.recorded.append(response)


def _request(question: str = "Why is Kalimantan Timur late so often?", mode: str = "ask_data") -> AskDataRequest:
    return AskDataRequest(session_id="s1", question=question, provider="gemini", model="m", mode=mode)  # type: ignore[arg-type]


def _collect(agent: AskDataAgent, request: AskDataRequest) -> list[dict[str, Any]]:
    async def go():
        return [event async for event in agent.stream(request)]

    return asyncio.run(go())


def test_open_questions_are_told_from_plain_ones() -> None:
    for text in ("Why is Kalimantan Timur late so often?", "What should we do about late deliveries?", "Kenapa tingkat keterlambatan tinggi?", "How can we reduce the late rate?"):
        assert is_open_question(text), text
    for text in ("Which region has the highest late delivery rate?", "How many orders per month?"):
        assert not is_open_question(text), text


def test_the_plan_drops_duplicates_documents_that_do_not_exist_and_extra_data_steps() -> None:
    raw = [AgentStep(kind="data", question=f"Late rate by {d}", why="w") for d in ("carrier", "region", "month", "channel", "category")]
    raw += [AgentStep(kind="data", question="late rate by carrier"), AgentStep(kind="knowledge", question="What does the policy say?")]
    steps = asyncio.run(plan_steps(Provider(raw), question="why", catalog=CATALOG, has_knowledge=False))
    assert [s.kind for s in steps] == ["data"] * 4
    with_docs = asyncio.run(plan_steps(Provider(raw[:2] + raw[-1:]), question="why", catalog=CATALOG, has_knowledge=True))
    assert [s.kind for s in with_docs] == ["data", "data", "knowledge"]


def test_each_step_runs_through_the_normal_pipeline_and_one_report_is_written() -> None:
    provider = Provider([AgentStep(kind="data", question="Late rate for Kalimantan Timur by carrier", why="Find where it comes from"), AgentStep(kind="data", question="Late rate for Kalimantan Timur by month"), AgentStep(kind="knowledge", question="When is a carrier review triggered?")])
    chat = Chat(provider, libraries=["lib1"])
    events = _collect(AskDataAgent(chat), _request())
    assert [e["stage"] for e in events if e["type"] == "progress"] == ["agent_plan", "agent_step", "agent_step", "agent_step", "agent_report"]
    done = events[-1]["response"]
    assert done.strategy == "agent" and done.status == "SUCCESS" and done.answer.direct_answer.startswith("Kalimantan Timur")
    assert [mode for mode, _ in chat.asked] == ["ask_data", "ask_data", "rag"]
    assert done.calculation.kind == "agent" and len(done.calculation.steps) == 3 and "Late rate · by carrier" in done.calculation.steps[0]
    assert done.citations and done.citations[0].filename == "Delivery_Returns_Policy.pdf"
    assert done.chart_spec is not None and done.data.row_count == 2  # the breakdown step supplies the table and chart
    assert done.usage and done.usage.llm_calls == 3
    assert chat.recorded == [done]
    assert provider.calls == ["AgentPlan", "AgentRefinement", "AnalysisOutput"]  # the refinement failed here, so the plan stood


def test_a_one_step_plan_is_completed_from_the_catalog_and_nothing_changes_when_steps_fail_or_the_mode_differs() -> None:
    # A small model often answers an overview with one step; the agent then adds the breakdowns an analyst would check.
    one = Chat(Provider([AgentStep(kind="data", question="Late rate", metric="late_delivery_rate")]))
    events = _collect(AskDataAgent(one), _request())
    assert events[-1]["type"] == "done" and events[-1]["response"].strategy == "agent"
    assert [q for _, q in one.asked] == ["Late rate", "late delivery rate per carrier"]
    bare = Chat(Provider([AgentStep(kind="data", question="Late rate")]))
    bare.metric_catalog = lambda: [{"name": "late_delivery_rate", "description": "Late delivery rate", "allowed_dimensions": []}]  # type: ignore[method-assign]
    assert _collect(AskDataAgent(bare), _request()) == [{"type": "progress", "stage": "agent_plan", "label": "Planning the analysis"}]
    assert bare.asked == []
    failing = Chat(Provider([AgentStep(kind="data", question="a"), AgentStep(kind="data", question="b")]), fail_data=True)
    assert not any(e["type"] == "done" for e in _collect(AskDataAgent(failing), _request()))
    rag = Chat(Provider([]))
    assert _collect(AskDataAgent(rag), _request(mode="rag")) == []
    assert _collect(AskDataAgent(rag), _request("Which region is highest?")) == []


def test_the_remaining_steps_are_adjusted_to_what_the_first_result_showed() -> None:
    plan = [
        AgentStep(kind="data", question="Late rate for Kalimantan Timur by carrier"),
        AgentStep(kind="data", question="Late rate for Kalimantan Timur by month"),
        AgentStep(kind="data", question="Late rate for Kalimantan Timur by region"),
    ]
    refined = [AgentStep(kind="data", question="Late rate for NusaCargo in Kalimantan Timur by month", why="NusaCargo stood out")]
    provider = Provider(plan, refined=refined)
    chat = Chat(provider)
    events = _collect(AskDataAgent(chat), _request())
    done = events[-1]["response"]
    assert [q for _, q in chat.asked] == ["Late rate for Kalimantan Timur by carrier", "Late rate for NusaCargo in Kalimantan Timur by month"]
    assert len(done.calculation.steps) == 2
    labels = [e["label"] for e in events if e["type"] == "progress" and e["stage"] == "agent_step"]
    assert labels[-1].startswith("Step 2 of 2")


def test_a_refinement_can_never_add_steps_or_repeat_one() -> None:
    plan = [AgentStep(kind="data", question="a overall"), AgentStep(kind="data", question="b"), AgentStep(kind="data", question="c")]
    refined = [AgentStep(kind="data", question="b"), AgentStep(kind="data", question="b"), AgentStep(kind="data", question="d"), AgentStep(kind="data", question="e")]
    chat = Chat(Provider(plan, refined=refined))
    _collect(AskDataAgent(chat), _request())
    assert [q for _, q in chat.asked] == ["a overall", "b", "d"]  # two remaining slots, duplicates dropped


def test_a_data_step_is_pinned_to_a_catalog_metric_and_an_invented_name_is_dropped() -> None:
    plan = [
        AgentStep(kind="data", question="Late rate for Kalimantan Timur", metric="late_delivery_rate"),
        AgentStep(kind="data", question="Late rate for Kalimantan Timur by carrier", metric="made_up_metric"),
        AgentStep(kind="data", question="Late rate by month", metric="late_delivery_rate"),
    ]
    chat = Chat(Provider(plan))
    _collect(AskDataAgent(chat), _request())
    pinned = [[(s.type, s.id) for s in (sources or [])] for sources in chat.sources]
    assert pinned[0] == [("semantic_metric", "late_delivery_rate")]
    assert pinned[1] == []  # not in the catalog: the step runs without a pin instead of with a wrong one
    assert pinned[2] == [("semantic_metric", "late_delivery_rate")]


def test_an_overview_without_a_usable_plan_gets_the_headline_volume_trend_and_standout_group() -> None:
    from app.ask_data.agent_mode import fallback_steps

    dims = ["delivery_shipments_shipment_id", "delivery_shipments_region_name", "delivery_shipments_carrier", "delivery_shipments_ship_date", "delivery_shipments_delivery_days"]
    catalog = [
        {"name": "total_orders", "description": "Total number of orders.", "allowed_dimensions": ["fulfillment_orders_order_date", "fulfillment_orders_channel"]},
        {"name": "average_delivery_days", "description": "Average days from ship to delivery.", "allowed_dimensions": dims},
        {"name": "late_delivery_rate", "description": "Share of shipments delivered late (%).", "allowed_dimensions": dims},
        {"name": "total_shipments", "description": "Number of shipments.", "allowed_dimensions": dims},
    ]
    steps = fallback_steps("Gimana performa pengiriman kita secara keseluruhan?", catalog, [], "id")
    assert [(s.metric, s.question) for s in steps] == [
        ("late_delivery_rate", "late delivery rate"),
        ("total_shipments", "total shipments"),
        ("late_delivery_rate", "late delivery rate per bulan"),
        ("late_delivery_rate", "late delivery rate per region"),
    ]
    # The planner's own step leads; the main rate of the same data follows.
    seeded = fallback_steps("How is delivery doing overall?", catalog, [AgentStep(kind="data", question="Average delivery days", metric="average_delivery_days")], "en")
    assert [s.metric for s in seeded][:2] == ["average_delivery_days", "late_delivery_rate"] and len(seeded) == 4


def test_the_catalog_plan_follows_the_conversation_and_checks_both_metrics_a_question_names() -> None:
    from app.ask_data.agent_mode import fallback_steps

    ship = ["delivery_shipments_region_name", "delivery_shipments_ship_date"]
    orders = ["fulfillment_orders_region_name", "fulfillment_orders_order_date"]
    catalog = [
        {"name": "total_orders", "description": "Total number of orders.", "allowed_dimensions": orders},
        {"name": "cancellation_rate", "description": "Share of cancelled orders (%).", "allowed_dimensions": orders},
        {"name": "late_delivery_rate", "description": "Share of shipments delivered late (%).", "allowed_dimensions": ship},
    ]
    # Nothing in the words names a metric: the one the conversation is about leads, not the first rate in the catalog.
    plain = fallback_steps("Kalau saya mau perbaiki satu hal dulu, sebaiknya mulai dari mana?", catalog, [], "id", current_metric="late_delivery_rate")
    assert plain[0].metric == "late_delivery_rate"
    both = fallback_steps("Berapa pesanan yang dibatalkan dan apakah ada hubungannya dengan keterlambatan?", catalog, [], "id")
    assert {"cancellation_rate", "late_delivery_rate"} <= {s.metric for s in both}
