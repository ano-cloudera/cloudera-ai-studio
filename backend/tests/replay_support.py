"""Run real conversations through the real ChatService against the sample fulfillment data, offline.

What is real: ChatService, the LangGraph workflow, the semantic context and its compiler, the follow-up engine, the
value filters, the comparisons, the verification and the answer checks. What is stood in: the data source (DuckDB over the
sample CSVs instead of Trino), the connector routing (a Trino-like context with qualified sources), the conversation store
(memory) and the language model (a scripted one). The scripted model deliberately behaves like the worst small model:
every question is called a follow-up on the first row of the previous result.
"""
from __future__ import annotations

import json
import pathlib
import tempfile
import uuid
from contextlib import nullcontext
from typing import Any

import duckdb

from app.core.models import AskDataRequest
from app.semantic.context import SemanticContextService

DATA = pathlib.Path(__file__).resolve().parents[2] / "samples" / "fulfillment" / "data"
ORDERS = {"order_id": "String", "order_date": "Date", "region_name": "String", "warehouse": "String", "channel": "String", "product_category": "String", "items": "Number", "order_value": "Number", "fulfillment_hours": "Number", "order_status": "String"}
SHIPMENTS = {"shipment_id": "String", "order_id": "String", "region_name": "String", "carrier": "String", "service_level": "String", "ship_date": "Date", "delivered_date": "Date", "delivery_days": "Number", "sla_days": "Number", "is_late": "String", "delivery_status": "String"}


def _fields(dataset: str, columns: dict[str, str], time: tuple[str, ...]) -> str:
    out = ""
    for name, datatype in columns.items():
        out += f"      - name: {dataset}_{name}\n        datatype: {datatype}\n        expression:\n          dialects:\n            - dialect: ANSI_SQL\n              expression: {name}\n"
        if name in time:
            out += "        dimension:\n          is_time: true\n"
    return out


def _metric(name: str, description: str, synonyms: str, expression: str, dataset: str, columns: dict[str, str]) -> str:
    allowed = ",".join(f'"{dataset}_{n}"' for n in columns)
    return (
        f"  - name: {name}\n    description: \"{description}\"\n    ai_context:\n      synonyms: {synonyms}\n    expression:\n      dialects:\n"
        f"        - dialect: ANSI_SQL\n          expression: {expression}\n    custom_extensions:\n      - vendor_name: REFERENCE\n"
        f"        data: '{{\"base_dataset\": \"{dataset}\", \"allowed_dimensions\": [{allowed}]}}'\n"
    )


def build_context() -> SemanticContextService:
    root = pathlib.Path(tempfile.mkdtemp()) / "rt"
    ossie = root / "ossie"
    ossie.mkdir(parents=True)
    core = (
        'version: "0.2.0.dev0"\nname: fulfillment\ndescription: x\ndatasets:\n'
        "  - name: fulfillment_orders\n    source: '\"hive\".\"default\".\"fulfillment_orders\"'\n    primary_key: [order_id]\n    fields:\n"
        + _fields("fulfillment_orders", ORDERS, ("order_date",))
        + "  - name: delivery_shipments\n    source: '\"hive\".\"default\".\"delivery_shipments\"'\n    primary_key: [shipment_id]\n    fields:\n"
        + _fields("delivery_shipments", SHIPMENTS, ("ship_date",))
        + "metrics:\n"
        + _metric("total_orders", "Total number of orders.", '["orders", "order count"]', "COUNT(order_id)", "fulfillment_orders", ORDERS)
        + _metric("total_order_value_idr", "Total order value in IDR.", '["order value", "nilai order", "revenue"]', "SUM(order_value)", "fulfillment_orders", ORDERS)
        + _metric("cancellation_rate", "Share of cancelled orders (%).", '["cancel rate", "cancellation rate"]', "COUNT(CASE WHEN order_status = 'Cancelled' THEN 1 END) * 100.0 / COUNT(order_id)", "fulfillment_orders", ORDERS)
        + _metric("late_delivery_rate", "Share of shipments delivered late (%).", '["late rate", "delay rate", "SLA breach rate"]', "COUNT(CASE WHEN is_late = 'true' THEN 1 END) * 100.0 / COUNT(shipment_id)", "delivery_shipments", SHIPMENTS)
        + _metric("total_shipments", "Number of shipments.", '["shipments", "parcels"]', "COUNT(shipment_id)", "delivery_shipments", SHIPMENTS)
    )
    (ossie / "reference_core.ossie.yaml").write_text(core)
    (ossie / "reference_governance.yaml").write_text('unknown_metric_question: "Which?"\n')
    (ossie / "golden_questions.yaml").write_text("questions: []\n")
    return SemanticContextService(root, validate_profile=False)


class DuckExecutor:
    """Runs the generated SQL on the sample CSVs and keeps every statement so a test can read what was asked."""

    def __init__(self) -> None:
        self.con = duckdb.connect()
        self.con.execute(f"CREATE TABLE fulfillment_orders AS SELECT * FROM read_csv_auto('{DATA / 'orders.csv'}')")
        self.con.execute(f"CREATE TABLE delivery_shipments AS SELECT * FROM read_csv_auto('{DATA / 'shipments.csv'}')")
        self.queries: list[str] = []

    def execute(self, sql: str, state: Any) -> dict[str, Any]:
        self.queries.append(" ".join(sql.split()))
        cursor = self.con.execute(sql.replace('"hive"."default".', ""))
        columns = [d[0] for d in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return {"columns": columns, "rows": rows, "row_count": len(rows), "execution_ms": 1}

    def scalar(self, sql: str) -> Any:
        return self.con.execute(sql).fetchone()[0]


class WorstCaseModel:
    """Writes a minimal answer, and calls every question a follow-up on the first row of the previous result."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def generate_structured(self, messages: list[dict[str, str]], model: Any, **_: Any) -> Any:
        self.calls.append(model.__name__)
        if model.__name__ == "AnalysisOutput":
            return model.model_validate(
                {"direct_answer": "ok", "executive_summary": "", "insights": [], "business_implications": [], "caveats": [], "data_reference": "x"}
            )
        question = ""
        for message in messages:
            if message.get("role") == "user":
                try:
                    payload = json.loads(message["content"])
                    question = payload.get("question") or payload.get("user_question") or question
                except Exception:  # noqa: BLE001 - not every user message is JSON
                    pass
        base = {"pipeline_question": question, "is_conversational": False, "attach_domain_catalog": False, "referential_follow_up": True, "follow_up_rank": 1}
        return model.model_validate({k: v for k, v in base.items() if k in model.model_fields})


class ScriptedModel(WorstCaseModel):
    """A model that rewrites follow-ups and picks metrics the way the prompts ask, from a script keyed by question."""

    def __init__(
        self,
        rewrites: dict[str, str] | None = None,
        choices: dict[str, str] | None = None,
        candidates: dict[str, list[str]] | None = None,
    ) -> None:
        super().__init__()
        self.rewrites = rewrites or {}
        self.choices = choices or {}
        self.candidates = candidates or {}
        self.payloads: list[dict[str, Any]] = []

    async def generate_structured(self, messages: list[dict[str, str]], model: Any, **kwargs: Any) -> Any:
        payload: dict[str, Any] = {}
        for message in messages:
            if message.get("role") == "user":
                try:
                    payload = json.loads(message["content"])
                except Exception:  # noqa: BLE001
                    pass
        question = str(payload.get("question") or "")
        if model.__name__ == "TurnReading":
            self.calls.append(model.__name__)
            self.payloads.append(payload)
            if question in self.rewrites:
                return model(kind="data", uses_previous=True, standalone_question=self.rewrites[question], rationale="script")
            return model(kind="data", uses_previous=False, standalone_question=question)
        if model.__name__ == "MetricChoice":
            self.calls.append(model.__name__)
            picked = self.choices.get(question, "")
            return model(metric=picked, confident=bool(picked), candidates=self.candidates.get(question, []))
        return await super().generate_structured(messages, model, **kwargs)


class MemoryHistory:
    def __init__(self) -> None:
        self.turns: dict[str, list[dict]] = {}

    def append(self, session_id, question, answer, rows, chart, provider, model, *, status="", strategy="", session_frame=None) -> None:  # noqa: ANN001
        self.turns.setdefault(session_id, []).append(
            {"question": question, "answer": answer.model_dump(), "rows": rows, "chart": chart.model_dump() if chart else None,
             "provider": provider, "model": model, "status": status, "strategy": strategy, "session_frame": session_frame or {}}
        )

    def load(self, session_id: str, limit: int = 20) -> list[dict]:
        return list(self.turns.get(session_id, []))[-limit:]

    def delete_session(self, session_id: str) -> int:
        return len(self.turns.pop(session_id, []))


class Turn:
    """One answer and the SQL that was sent to the data source for it; attribute access falls through to the answer."""

    def __init__(self, response: Any, queries: list[str]) -> None:
        self._response = response
        self.queries_run = queries

    def __getattr__(self, name: str) -> Any:
        return getattr(self._response, name)


class Replay:
    """One conversation: `ask` sends a question in the same session and returns the response."""

    def __init__(self, monkeypatch: Any, model: Any = None) -> None:
        from app.ask_data import datasource_router as router_module
        from app.ask_data.types import DatasourceExecutionContext
        from app.graph.workflow import WorkflowDependencies
        from app.projects import resolver as resolver_module
        from app.semantic_runtime.loader import RuntimeContextBundle, SemanticRuntimeLoader
        from app.services.chat import ChatService
        from app.sql.validator import ValidatedSQL
        from conftest import isolated_settings

        self.context = build_context()
        self.executor = DuckExecutor()
        self.model = model or WorstCaseModel()
        settings = isolated_settings(state_store="memory")

        class Registry:
            def resolve(_self, provider: str, model: str) -> Any:  # noqa: N805
                return self.model

        class Router:
            def __init__(_self, session: Any, settings: Any = None) -> None:  # noqa: N805
                pass

            def resolve_for_governed_metric(_self, *, dataset_name: str, **_: Any) -> Any:  # noqa: N805
                return DatasourceExecutionContext(
                    legacy_fallback=False, connector_id=uuid.uuid4(), connector_type="trino", connector_name="replay", dialect="trino",
                    qualified_sources={n: f'"hive"."default"."{n}"' for n in ("fulfillment_orders", "delivery_shipments")},
                    allowed_physical_tables=frozenset({"fulfillment_orders", "delivery_shipments"}),
                )

        monkeypatch.setattr(router_module, "AskDataDatasourceRouter", Router)
        monkeypatch.setattr(resolver_module, "load_default_project", lambda s: type("P", (), {"workspace_id": uuid.uuid4(), "id": uuid.uuid4(), "project_id": None})())
        bundle = RuntimeContextBundle(context=self.context, mode="runtime", deployment_id=None, semantic_version_id=None, registry_version_number=1, artifact_checksum="replay", health="HEALTHY")
        monkeypatch.setattr(SemanticRuntimeLoader, "_instance", None)
        SemanticRuntimeLoader.get(settings).swap_bundle(bundle)
        dependencies = WorkflowDependencies(
            semantic_context=self.context, provider_registry=Registry(), query_executor=self.executor,
            sql_validator=lambda sql, state: ValidatedSQL(True, sql=sql), validation_context=self.context,
            judge_enabled=False, settings=settings, session_factory=lambda: nullcontext(),
        )
        self.service = ChatService(settings, dependencies=dependencies, history=MemoryHistory())
        self.service.apply_runtime_bundle(bundle)
        self.session_id = f"replay-{uuid.uuid4().hex[:6]}"

    async def ask(self, question: str) -> Any:
        before = len(self.executor.queries)
        response = await self.service.run(AskDataRequest(session_id=self.session_id, question=question, provider="qwen", model="/models/Qwen3.8-27B-AWQ"))
        return Turn(response, self.executor.queries[before:])
