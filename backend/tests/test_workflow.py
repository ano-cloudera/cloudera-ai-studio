from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from app.core.models import AnalysisOutput, AskDataRequest, QueryPlan
from app.graph.workflow import WorkflowDependencies, build_workflow
from app.sql.validator import ValidatedSQL


class FakeProvider:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.calls: list[str] = []

    async def generate_structured(self, messages, response_model, **kwargs):
        self.calls.append(response_model.__name__)
        self.messages = messages
        return response_model.model_validate(self.responses.pop(0))


class FakeRegistry:
    def __init__(self, provider: FakeProvider) -> None:
        self.provider = provider

    def resolve(self, provider: str, model: str):
        return self.provider


class FakeContext:
    def __init__(self, resolution: dict, sql: str = "SELECT d.material FROM gold.allowed d LIMIT 10") -> None:
        self.resolution = resolution
        self.sql = sql
        base_dataset = (resolution.get("definition") or {}).get("base_dataset", "material_360")
        self.registry = type("Reg", (), {"dataset_fields": {base_dataset: frozenset()}})()

    def resolve(self, question: str, session_last_metric=None, session_analysis_context=None, **kwargs):
        return self.resolution

    def metric_definition(self, metric: str):
        return self.resolution.get("definition") or {"base_dataset": "material_360"}

    def planner_context(self, domains=None):
        return {"datasets": [{"view": "gold.allowed", "columns": ["material", "value"]}]}

    def greeting_context(self):
        return {"scope": "October-December 2024", "domains": ["Sales / Sell-In", "B2B / Sell-Out"]}

    def guidance_context(self, question: str, **kwargs):
        return {
            "scope": "October-December 2024",
            "domains": ["Sales / Sell-In", "Stock Tempo", "Stock SAT (Alfamart)"],
            "focus": "stock" if "stok" in question.casefold() else None,
            "metrics": [{"name": "sat_store_stock_quantity", "dimensions": ["division", "plu"]}],
            "examples": ["Berapa stok retail per division?"],
        }

    def compile_governed(self, metric: str, question: str, requested_dimensions=None, extra_predicates=None, **kwargs):
        _ = extra_predicates
        _ = kwargs
        return self.sql

    def domain_capability_insight_lines(self, *, exclude_focus: str | None = None, language: str = "en"):
        lines = [f"Domain insight {i}" for i in range(9)]
        if exclude_focus:
            return [line for line in lines if exclude_focus not in line.casefold()]
        return lines


class FakeExecutor:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.queries: list[str] = []

    def execute(self, sql: str, state):
        self.queries.append(sql)
        return {"columns": list(self.rows[0]) if self.rows else [], "rows": self.rows, "row_count": len(self.rows), "execution_ms": 4}


@dataclass
class FakeValidationContext:
    pass


def analysis(chart_spec=None):
    return {
        "direct_answer": "Jawaban grounded",
        "executive_summary": "Ringkasan",
        "insights": ["Insight"],
        "business_implications": ["Implikasi"],
        "caveats": [],
        "data_reference": "actual query result",
        "chart_spec": chart_spec,
    }


def deps(context, provider, rows, validator=lambda sql, context: ValidatedSQL(True, sql=sql)):
    return WorkflowDependencies(
        semantic_context=context,
        provider_registry=FakeRegistry(provider),
        query_executor=FakeExecutor(rows),
        sql_validator=validator,
        validation_context=FakeValidationContext(),
        judge_enabled=False,
    )


@pytest.mark.asyncio
async def test_governed_path_uses_deterministic_plan_and_grounded_analysis() -> None:
    provider = FakeProvider([analysis({"type": "bar", "title": "By material", "x": "material", "y": "value"})])
    context = FakeContext({"status": "resolved", "metric": "material_sell_in_value", "definition": {"base_dataset": "material_360"}})
    dependencies = deps(context, provider, [{"material": "A", "value": 10}])

    state = await build_workflow(dependencies).ainvoke(AskDataRequest(session_id="s1", question="top material", provider="qwen", model="qwen-model").model_dump())

    assert state["status"] == "SUCCESS"
    assert state["strategy"] == "governed"
    assert provider.calls == ["AnalysisOutput"]
    assert state["chart_spec"]["x"] == "material"
    assert state["timings"]["validation_ms"] >= 0


@pytest.mark.asyncio
async def test_data_reference_is_always_the_view_name_never_the_raw_sql() -> None:
    """Even if the model writes the full SQL statement into data_reference
    (as observed live), the final answer must only ever cite the view
    name(s) actually executed - never expose the SELECT statement to a
    business user."""
    provider = FakeProvider([
        analysis() | {"data_reference": "SELECT SUM(d.sales_bill_val) AS metric_value FROM gold.rpt_sap_monthly_executive_semantic d WHERE d.calmonth BETWEEN 202410 AND 202412"}
    ])
    context = FakeContext(
        {"status": "resolved", "metric": "gross_billing_value", "definition": {"base_dataset": "monthly_executive"}},
        sql="SELECT SUM(d.sales_bill_val) AS metric_value FROM gold.rpt_sap_monthly_executive_semantic d WHERE d.calmonth BETWEEN 202410 AND 202412",
    )
    dependencies = deps(context, provider, [{"metric_value": 3841865787074}])

    state = await build_workflow(dependencies).ainvoke(
        AskDataRequest(session_id="s1", question="gross sell in q4", provider="qwen", model="qwen-model").model_dump()
    )

    assert state["answer"]["data_reference"] == "gold.rpt_sap_monthly_executive_semantic"
    assert "SELECT" not in state["answer"]["data_reference"]


@pytest.mark.asyncio
async def test_controlled_fallback_uses_exactly_planner_then_analyst() -> None:
    provider = FakeProvider([
        {"strategy": "sql_fallback", "domains": ["sales"], "metrics": [], "dimensions": ["material"], "filters": {}, "analysis_type": "ranking", "sql": "SELECT d.material, d.value FROM gold.allowed d LIMIT 10", "clarification_question": None},
        analysis(),
    ])
    dependencies = deps(FakeContext({"status": "fallback", "reason": "no_published_metric_match"}), provider, [{"material": "A", "value": 10}])

    state = await build_workflow(dependencies).ainvoke(AskDataRequest(session_id="s1", question="fallback", provider="gemini", model="gemini-model").model_dump())

    assert state["status"] == "SUCCESS"
    assert state["strategy"] == "sql_fallback"
    assert provider.calls == ["QueryPlan", "AnalysisOutput"]


@pytest.mark.asyncio
async def test_dimension_mismatch_uses_governed_sql_and_appends_partial_caveats() -> None:
    provider = FakeProvider([analysis()])
    context = FakeContext({
        "status": "resolved",
        "metric": "gross_billing_value",
        "definition": {"base_dataset": "monthly_executive"},
        "dimension_mismatch": ["material"],
    })

    dependencies = deps(context, provider, [{"material": "A", "value": 10}])
    state = await build_workflow(dependencies).ainvoke(
        AskDataRequest(session_id="s1", question="Sell-In per material", provider="qwen", model="qwen-model").model_dump()
    )

    assert state["status"] == "SUCCESS"
    assert state["strategy"] == "governed"
    assert provider.calls == ["AnalysisOutput"]
    assert dependencies.query_executor.queries == [context.sql]
    assert any("material/produk/SKU" in caveat for caveat in state["answer"]["caveats"])


@pytest.mark.asyncio
async def test_entity_lookup_with_null_metric_value_returns_no_data() -> None:
    provider = FakeProvider([])
    sql = "SELECT d.material, NULL AS metric_value FROM gold.allowed d WHERE d.material = '500-21-02' LIMIT 1"
    context = FakeContext(
        {
            "status": "resolved",
            "metric": "months_of_stock_cover",
            "definition": {"base_dataset": "material_360"},
            "dimensions": ["material"],
            "dimension_mismatch": ["branch"],
        },
        sql=sql,
    )
    context.registry = type(
        "Reg",
        (),
        {
            "dataset_fields": {
                "material_360": frozenset(
                    {"material", "calmonth", "warehouse_stock_qty", "sell_in_bill_qty", "has_sell_in", "has_stock"}
                ),
            },
        },
    )()
    dependencies = deps(context, provider, [{"material": "500-21-02", "metric_value": None}])
    state = await build_workflow(dependencies).ainvoke(
        AskDataRequest(
            session_id="s1",
            question="material 500-21-02 di cabang 0201 cover stok",
            provider="qwen",
            model="qwen-model",
        ).model_dump()
    )

    assert state["status"] == "NO_DATA"
    assert provider.calls == []
    assert "sell-in nol" in state["answer"]["direct_answer"].casefold() or "tidak ada nilai" in state["answer"]["direct_answer"].casefold()


@pytest.mark.asyncio
async def test_stock_cover_with_branch_mismatch_runs_governed_with_cover_caveats() -> None:
    provider = FakeProvider([analysis()])
    sql = "SELECT d.material, SUM(d.warehouse_stock_qty) FROM gold.rpt_sap_material_month_semantic d LIMIT 10"
    context = FakeContext(
        {
            "status": "resolved",
            "metric": "months_of_stock_cover",
            "definition": {"base_dataset": "material_360"},
            "dimensions": ["material"],
            "dimension_mismatch": ["branch"],
        },
        sql=sql,
    )
    dependencies = deps(context, provider, [{"material": "500-21-02", "metric_value": 2.5}])
    question = (
        "produk material 500-21-02 di cabang 0201 hitung cover penjualan berapa hari dari stok"
    )
    state = await build_workflow(dependencies).ainvoke(
        AskDataRequest(session_id="s1", question=question, provider="qwen", model="qwen-model").model_dump()
    )

    assert state["status"] == "SUCCESS"
    assert state["strategy"] == "governed"
    assert provider.calls == ["AnalysisOutput"]
    caveats = " ".join(state["answer"]["caveats"])
    assert "cabang/DC partner" in caveats
    assert "bulan" in caveats


@pytest.mark.asyncio
async def test_clarification_and_unsupported_do_not_execute_query() -> None:
    clarification_provider = FakeProvider([])
    clarification = deps(FakeContext({"status": "needs_clarification", "question": "Sell-In atau Sell-Out?", "options": []}), clarification_provider, [])
    state = await build_workflow(clarification).ainvoke(AskDataRequest(session_id="s", question="total sales", provider="qwen", model="m").model_dump())
    assert state["status"] == "CLARIFICATION"
    assert state["answer"]["direct_answer"] == "Sell-In atau Sell-Out?"
    assert clarification.query_executor.queries == []

    semantic_unsupported = deps(FakeContext({"status": "unsupported"}), FakeProvider([]), [])
    state = await build_workflow(semantic_unsupported).ainvoke(AskDataRequest(session_id="s", question="biaya iklan TV", provider="qwen", model="m").model_dump())
    assert state["status"] == "CLARIFICATION"
    assert semantic_unsupported.query_executor.queries == []

    unsupported_provider = FakeProvider([{"strategy": "unsupported", "domains": [], "metrics": [], "dimensions": [], "filters": {}, "analysis_type": "unsupported", "sql": None, "clarification_question": None}])
    unsupported = deps(FakeContext({"status": "fallback", "reason": "no_published_metric_match"}), unsupported_provider, [])
    state = await build_workflow(unsupported).ainvoke(AskDataRequest(session_id="s", question="biaya iklan TV", provider="qwen", model="m").model_dump())
    assert state["status"] == "UNSUPPORTED"
    assert unsupported.query_executor.queries == []


class FakeLocalAgentClient:
    def __init__(self, *, enabled: bool = True, payload: dict | None = None, error: Exception | None = None) -> None:
        self.enabled = enabled
        self.payload = payload
        self.error = error
        self.calls: list[str] = []

    async def query(self, question: str, *, answer_language: str = "id"):
        self.calls.append(question)
        if self.error is not None:
            raise self.error
        return self.payload


@pytest.mark.asyncio
async def test_unsupported_plan_falls_through_unchanged_when_local_agent_disabled() -> None:
    """No local_agent_client configured (the default for every deployment
    that hasn't opted in) must behave exactly like before this feature was
    added - UNSUPPORTED, no extra calls, no exceptions."""
    provider = FakeProvider([{"strategy": "unsupported", "domains": [], "metrics": [], "dimensions": [], "filters": {}, "analysis_type": "unsupported", "sql": None, "clarification_question": None}])
    dependencies = deps(FakeContext({"status": "fallback", "reason": "no_published_metric_match"}), provider, [])
    assert dependencies.local_agent_client is None

    state = await build_workflow(dependencies).ainvoke(AskDataRequest(session_id="s", question="biaya iklan TV", provider="qwen", model="m").model_dump())

    assert state["status"] == "UNSUPPORTED"
    assert state["strategy"] == "unsupported"


@pytest.mark.asyncio
async def test_unsupported_plan_uses_local_agent_fallback_when_it_answers() -> None:
    provider = FakeProvider([{"strategy": "unsupported", "domains": [], "metrics": [], "dimensions": [], "filters": {}, "analysis_type": "unsupported", "sql": None, "clarification_question": None}])
    dependencies = deps(FakeContext({"status": "fallback", "reason": "no_published_metric_match"}), provider, [])
    dependencies.local_agent_client = FakeLocalAgentClient(payload={
        "resolved_query_ids": ["SI-01@calquarter_material"],
        "final_response_markdown": "## Answer\n\nTop 5 produk dengan sell-in tertinggi...\n\n## Routing\n\n(details omitted)",
    })

    state = await build_workflow(dependencies).ainvoke(
        AskDataRequest(session_id="s", question="top 5 produk berdasarkan sell-in", provider="qwen", model="m").model_dump()
    )

    assert state["status"] == "SUCCESS"
    assert state["strategy"] == "local_agent_exploratory"
    assert "Top 5 produk" in state["answer"]["direct_answer"]
    assert "Routing" not in state["answer"]["direct_answer"]
    assert any("eksploratif" in caveat.casefold() for caveat in state["answer"]["caveats"])
    assert "SI-01@calquarter_material" in state["answer"]["data_reference"]
    assert dependencies.local_agent_client.calls == ["top 5 produk berdasarkan sell-in"]


@pytest.mark.asyncio
async def test_picking_unloading_planner_clarification_tries_local_agent_second() -> None:
    question = (
        "Analisa data unloading dan picking dan berikan Analisa dan perbandingan dengan Industri standard"
    )
    provider = FakeProvider([{
        "strategy": "clarification",
        "domains": [],
        "metrics": [],
        "dimensions": [],
        "filters": {},
        "analysis_type": "clarification",
        "sql": None,
        "clarification_question": "Standar industri apa yang ingin digunakan?",
    }])
    dependencies = deps(FakeContext({
        "status": "fallback",
        "reason": "multi_concept_metric_mismatch",
    }), provider, [])
    dependencies.local_agent_client = FakeLocalAgentClient(payload={
        "resolved_query_ids": ["PK-03@company_period_delta"],
        "final_response_markdown": "## Answer\n\nAnalisis picking vs benchmark internal...",
    })

    state = await build_workflow(dependencies).ainvoke(
        AskDataRequest(session_id="s", question=question, provider="qwen", model="m").model_dump()
    )

    assert state["status"] == "SUCCESS"
    assert state["strategy"] == "local_agent_exploratory"
    assert provider.calls == ["QueryPlan"]
    assert dependencies.local_agent_client.calls == [question]


@pytest.mark.asyncio
async def test_resolver_sell_in_clarification_does_not_skip_to_local_agent() -> None:
    provider = FakeProvider([])
    dependencies = deps(FakeContext({
        "status": "needs_clarification",
        "question": "Sell-In atau Sell-Out?",
        "options": [],
    }), provider, [])
    dependencies.local_agent_client = FakeLocalAgentClient(payload={
        "final_response_markdown": "## Answer\n\nShould not be used",
    })

    state = await build_workflow(dependencies).ainvoke(
        AskDataRequest(session_id="s", question="Top 10 produk penjualan di Tempo", provider="qwen", model="m").model_dump()
    )

    assert state["status"] == "CLARIFICATION"
    assert dependencies.local_agent_client.calls == []


@pytest.mark.asyncio
async def test_uat_branch_sl_question_uses_governed_sales_office_path() -> None:
    from app.semantic.context import SemanticContextService

    question = "Hitung service level/ fill rate di cabang tempo dan urutkan SL terjelek"
    provider = FakeProvider([analysis()])
    dependencies = deps(SemanticContextService(), provider, [{"sales_off": "0201", "metric_value": 0.42}])

    state = await build_workflow(dependencies).ainvoke(
        AskDataRequest(session_id="s", question=question, provider="qwen", model="m").model_dump()
    )

    assert state["status"] == "SUCCESS"
    assert state["strategy"] == "governed"
    assert "corr_service_sales_office_material_month" in (state.get("sql") or "")
    assert "ORDER BY metric_value ASC" in (state.get("sql") or "")
    assert provider.calls == ["AnalysisOutput"]


@pytest.mark.asyncio
async def test_unsupported_plan_falls_through_unchanged_when_local_agent_errors() -> None:
    """A broken/unreachable local agent must never turn a normal unsupported
    answer into a request failure - it degrades to the exact same message
    as if the fallback didn't exist."""
    provider = FakeProvider([{"strategy": "unsupported", "domains": [], "metrics": [], "dimensions": [], "filters": {}, "analysis_type": "unsupported", "sql": None, "clarification_question": None}])
    dependencies = deps(FakeContext({"status": "fallback", "reason": "no_published_metric_match"}), provider, [])
    dependencies.local_agent_client = FakeLocalAgentClient(error=RuntimeError("connection refused"))

    state = await build_workflow(dependencies).ainvoke(
        AskDataRequest(session_id="s", question="biaya iklan TV", provider="qwen", model="m").model_dump()
    )

    assert state["status"] == "UNSUPPORTED"
    assert state["strategy"] == "unsupported"
    assert dependencies.local_agent_client.calls == ["biaya iklan TV"]


@pytest.mark.asyncio
async def test_unsupported_plan_ignores_a_disabled_local_agent_client() -> None:
    provider = FakeProvider([{"strategy": "unsupported", "domains": [], "metrics": [], "dimensions": [], "filters": {}, "analysis_type": "unsupported", "sql": None, "clarification_question": None}])
    dependencies = deps(FakeContext({"status": "fallback", "reason": "no_published_metric_match"}), provider, [])
    dependencies.local_agent_client = FakeLocalAgentClient(enabled=False, payload={"final_response_markdown": "## Answer\n\nShould never be reached"})

    state = await build_workflow(dependencies).ainvoke(
        AskDataRequest(session_id="s", question="biaya iklan TV", provider="qwen", model="m").model_dump()
    )

    assert state["status"] == "UNSUPPORTED"
    assert dependencies.local_agent_client.calls == []


@pytest.mark.asyncio
async def test_invalid_sql_gets_only_one_repair_attempt() -> None:
    provider = FakeProvider([
        {"strategy": "sql_fallback", "domains": ["sales"], "metrics": [], "dimensions": [], "filters": {}, "analysis_type": "metric", "sql": "DROP TABLE x", "clarification_question": None},
        {"strategy": "sql_fallback", "domains": ["sales"], "metrics": [], "dimensions": [], "filters": {}, "analysis_type": "metric", "sql": "SELECT d.value FROM gold.allowed d LIMIT 10", "clarification_question": None},
        analysis(),
    ])
    attempts = 0

    def validator(sql, context):
        nonlocal attempts
        attempts += 1
        return ValidatedSQL(attempts > 1, sql=sql if attempts > 1 else None, error=None if attempts > 1 else "DDL/DML statements are not allowed")

    state = await build_workflow(deps(FakeContext({"status": "fallback", "reason": "no_published_metric_match"}), provider, [{"value": 1}], validator)).ainvoke(AskDataRequest(session_id="s", question="fallback", provider="openai", model="m").model_dump())

    assert state["status"] == "SUCCESS"
    assert state["retry_count"] == 1
    assert attempts == 2
    assert provider.calls == ["QueryPlan", "QueryPlan", "AnalysisOutput"]


@pytest.mark.asyncio
async def test_empty_result_is_no_data_and_invalid_chart_is_removed() -> None:
    no_data_provider = FakeProvider([])
    governed = FakeContext({"status": "resolved", "metric": "gross_billing_value", "definition": {"base_dataset": "monthly_executive"}})
    no_data = await build_workflow(deps(governed, no_data_provider, [])).ainvoke(AskDataRequest(session_id="s", question="gross", provider="qwen", model="m").model_dump())
    assert no_data["status"] == "NO_DATA"
    assert no_data_provider.calls == []

    invalid_chart_provider = FakeProvider([analysis({"type": "bar", "title": "Wrong", "x": "missing", "y": "value"})])
    invalid_chart = await build_workflow(deps(governed, invalid_chart_provider, [{"value": 1}])).ainvoke(AskDataRequest(session_id="s", question="gross", provider="qwen", model="m").model_dump())
    assert invalid_chart["chart_spec"] is None


@pytest.mark.asyncio
async def test_greeting_is_written_by_selected_llm_without_querying_impala() -> None:
    provider = FakeProvider([analysis() | {
        "direct_answer": "Halo! Senang bisa bantu 👋",
        "executive_summary": "Saya bisa bantu membaca data komersial TEMPO Q4 2024.",
        "insights": ["Coba tanyakan Gross Sales atau Sell-Out."],
        "business_implications": [],
        "data_reference": "TEMPO governed capability catalog.",
    }])
    dependencies = deps(FakeContext({"status": "unsupported"}), provider, [])

    state = await build_workflow(dependencies).ainvoke({
        **AskDataRequest(session_id="s1", question="Halo", provider="qwen", model="qwen-model").model_dump(),
        "conversation_history": [],
        "turn_understanding": {
            "is_conversational": True,
            "attach_domain_catalog": True,
            "pipeline_question": "Halo",
            "rationale": "test",
        },
    })

    assert state["status"] == "SUCCESS"
    assert state["strategy"] == "conversational"
    assert state["answer"]["direct_answer"].startswith("Halo!")
    assert len(state["answer"]["insights"]) == 9
    assert dependencies.query_executor.queries == []
    assert provider.calls == ["AnalysisOutput"]


@pytest.mark.asyncio
@pytest.mark.parametrize("question", [
    "hallo apa yang bisa anda bantu hari ini?",
    "selamat pagi",
    "kamu bisa bantu apa lagi selain data sales?",
    "mau tau tentang data stok dong bisa keluarin apa aja?",
    "hallo kamu bintu apa ?",
    "kamu bintu apa ?",
])
async def test_capability_conversation_is_guided_by_selected_llm_without_sql(question: str) -> None:
    provider = FakeProvider([analysis() | {
        "direct_answer": "Bisa. Untuk stok, saya bisa bantu beberapa arah analisis.",
        "executive_summary": "Pilih stok Tempo, DC partner, atau retail store.",
        "insights": ["Contoh: berapa stok retail per division?"],
        "business_implications": [],
        "data_reference": "TEMPO governed capability catalog.",
    }])
    dependencies = deps(FakeContext({"status": "unsupported"}), provider, [])
    attach_catalog = "stok" not in question.casefold()

    state = await build_workflow(dependencies).ainvoke({
        **AskDataRequest(session_id="s1", question=question, provider="qwen", model="qwen-model").model_dump(),
        "original_question": question,
        "conversation_history": [{"question": "sebelumnya", "answer": {"direct_answer": "jawaban"}}],
        "turn_understanding": {
            "is_conversational": True,
            "attach_domain_catalog": attach_catalog,
            "pipeline_question": question,
            "rationale": "test",
        },
    })

    assert state["status"] == "SUCCESS"
    assert state["strategy"] == "conversational"
    assert dependencies.query_executor.queries == []
    payload = provider.messages[1]["content"]
    assert "conversation_history" in payload
    if "stok" in question:
        assert "sat_store_stock_quantity" in payload


@pytest.mark.asyncio
async def test_understand_preserves_precomputed_follow_up_resolution() -> None:
    """ChatService resolves follow-ups with session context; workflow must not re-resolve without it."""
    provider = FakeProvider([analysis()])
    follow_resolution = {
        "status": "resolved",
        "metric": "b2b_material_plu_value",
        "matched_alias": "follow_up_context",
        "dimensions": ["material"],
        "dimension_mismatch": ["branch"],
        "definition": {
            "base_dataset": "b2b_material_plu",
            "allowed_dimensions": ["calmonth", "material", "kode_plu"],
            "expression": "SUM(b2b_material_plu.b2b_bill_val)",
        },
    }
    context = FakeContext(follow_resolution, sql="SELECT d.material FROM gold.corr_b2b_material_plu d LIMIT 3")
    context.registry = type(
        "Reg",
        (),
        {"dataset_fields": {"b2b_material_plu": frozenset({"material", "calmonth", "b2b_bill_val"})}},
    )()
    resolve_calls = {"n": 0}
    original_resolve = context.resolve

    def counting_resolve(question, session_last_metric=None, session_analysis_context=None):
        resolve_calls["n"] += 1
        return original_resolve(question, session_last_metric, session_analysis_context)

    context.resolve = counting_resolve  # type: ignore[method-assign]
    dependencies = deps(context, provider, [{"material": "500-21-02", "metric_value": 100}])
    payload = {
        **AskDataRequest(
            session_id="s-follow",
            question="breakdown cabang palembang top 3 produk",
            provider="qwen",
            model="qwen-model",
        ).model_dump(),
        "semantic_resolution": follow_resolution,
        "session_last_metric": "b2b_branch_sell_out_value",
    }
    state = await build_workflow(dependencies).ainvoke(payload)
    assert resolve_calls["n"] == 0
    assert state["status"] == "SUCCESS"
    assert state["semantic_resolution"]["metric"] == "b2b_material_plu_value"
    assert "corr_b2b_material_plu" in dependencies.query_executor.queries[0]


def test_query_plan_cannot_select_conversational_strategy() -> None:
    with pytest.raises(ValidationError):
        QueryPlan.model_validate({"strategy": "conversational"})
