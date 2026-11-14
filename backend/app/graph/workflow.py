from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from langgraph.graph import END, START, StateGraph

from app.core.language import detect_language
from app.core.models import AnalysisOutput, QueryPlan
from app.graph.inquiry_brief import build_inquiry_brief
from app.graph.judge import judge_review
from app.graph.judge_replan import apply_judge_replan
from app.graph.state import AskDataState
from app.llm.base import LLMProvider, ProviderError
from app.ask_data.conversation import TurnReading, reading_from_state
from app.services.user_facing_error import explain_failure
from app.sql.validator import ValidatedSQL


logger = logging.getLogger(__name__)


PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"


@dataclass
class WorkflowDependencies:
    semantic_context: Any
    provider_registry: Any
    query_executor: Any
    sql_validator: Callable[[str, Any], ValidatedSQL]
    validation_context: Any
    settings: Any = None
    session_factory: Any = None
    judge_max_iterations: int = 2
    judge_enabled: bool = True
    usage_tracker: Any = None


def _elapsed(started: float) -> float:
    return round((perf_counter() - started) * 1000, 3)


def _prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def _ask_data_global_system() -> str:
    from app.core.config import get_settings
    from app.prompt_management.keys import ASK_DATA_SYSTEM
    from app.prompt_management.resolver import PromptResolver

    settings = get_settings()
    text = PromptResolver(settings).resolve(ASK_DATA_SYSTEM).content.strip()
    return text or _prompt("global_system.md")


def _provider(state: AskDataState, deps: WorkflowDependencies) -> LLMProvider:
    provider = deps.provider_registry.resolve(state["provider"], state["model"])
    if deps.usage_tracker is not None:
        return deps.usage_tracker.wrap(provider, state["request_id"])
    return provider


def _with_timing(state: AskDataState, key: str, value: float) -> dict[str, float]:
    return {**state.get("timings", {}), key: value}


_TABLE_REF_RE = re.compile(r"\bFROM\s+([a-zA-Z_][\w]*\.[a-zA-Z_][\w]*)", re.IGNORECASE)


def _data_reference_from_sql(sql: str) -> str | None:
    """Extract just the gold.<view> name(s) referenced by the executed SQL,
    never the SQL text itself - the analyst's data_reference must stay a
    citation a business user can read, not an implementation detail a raw
    SELECT statement exposes."""
    matches = _TABLE_REF_RE.findall(sql or "")
    if not matches:
        return None
    seen: list[str] = []
    for name in matches:
        if name not in seen:
            seen.append(name)
    return ", ".join(seen)


async def _top_groups_first(intent: dict[str, Any], metric: str, from_source: str | None, state: dict[str, Any], deps: Any) -> dict[str, Any]:
    """'Top 3 provinces by month': first ask which 3 (one governed query by province, ordered and limited), then return the
    intent filtered to them and without the limit, so every month of each is shown. Two plain queries, each one the SQL check
    accepts; when the first cannot run, the series is shown for all groups rather than cut."""
    breakdown = [str(k) for k in intent.get("breakdown") or []]
    if not (intent.get("limit") and intent.get("time_key") and len(breakdown) == 1 and from_source):
        return intent
    import inspect

    top_sql = deps.semantic_context.compile_intent(metric, {**intent, "time_key": None}, from_source=from_source)
    try:
        checked = deps.sql_validator(top_sql, state)
        if not getattr(checked, "valid", False):
            return {**intent, "limit": None}
        result = deps.query_executor.execute(getattr(checked, "sql", None) or top_sql, {**state, "context_query": True})
        if inspect.isawaitable(result):
            result = await result
    except Exception:  # noqa: BLE001 - the full series is still a right answer
        logger.warning("top_groups_query_failed metric=%s", metric)
        return {**intent, "limit": None}
    values = [str(row.get(breakdown[0])) for row in (result.get("rows") or []) if row.get(breakdown[0]) is not None]
    if not values:
        return {**intent, "limit": None}
    filters = [f for f in intent.get("filters") or [] if f.get("dimension") != breakdown[0]]
    return {**intent, "filters": [*filters, {"dimension": breakdown[0], "values": values}], "limit": None}


def _overall_figures(value: Any) -> list[float]:
    """The overall value the analyst was given beside the breakdown, as figures the answer may quote."""
    try:
        return [float(value)] if value is not None and not isinstance(value, bool) else []
    except (TypeError, ValueError):
        return []


def _governed_partial_caveats(resolution: dict[str, Any], language: str = "en") -> list[str]:
    unmet = list(resolution.get("dimension_mismatch") or [])
    if not unmet:
        return []
    metric = str(resolution.get("metric") or "")
    labels = [name.replace("_", " ") for name in unmet]
    if language == "id":
        return [
            f"Breakdown per {' dan '.join(labels)} tidak tersedia untuk metrik {metric} di semantic model. "
            "Angka di bawah hanya mencakup breakdown yang didukung metrik ini."
        ]
    return [
        f"A breakdown by {' and '.join(labels)} is not available for {metric} in the semantic model. "
        "The figures below only cover the breakdowns this metric supports."
    ]


def _safe_answer(text: str, *, caveats: list[str] | None = None) -> dict[str, Any]:
    return AnalysisOutput(
        direct_answer=text,
        executive_summary=text,
        insights=[],
        business_implications=[],
        caveats=caveats or [],
        data_reference="No query result was used.",
        chart_spec=None,
    ).model_dump()


def _assistant_name(deps: WorkflowDependencies) -> str:
    name = getattr(deps.settings, "assistant_name", "") if deps.settings is not None else ""
    if not name:
        from app.core.config import get_settings

        name = get_settings().assistant_name
    return str(name or "Anywhere AI Studio")


_GENERIC_TITLES = {"chart", "grafik", "result", "results", "hasil", "data", "table", "tabel", "kpi", "metric", "metrik"}


def _title_is_the_question(title: str | None, *questions: str) -> bool:
    """A title that says nothing of its own: empty, generic ("Chart") or a copy of the question."""
    text = " ".join((title or "").casefold().split())
    if not text or text in _GENERIC_TITLES:
        return True
    if text.endswith("?"):
        return True
    return any(text == " ".join(q.casefold().split())[: len(text)] and len(text) > 20 for q in questions if q)


def _titled(label: str, by: str | None, question: str) -> str:
    """A chart's title in the words of the question: "Tingkat Keterlambatan per Regional", "Late rate by Region"."""
    if not by:
        return label
    return f"{label} {'per' if detect_language(question) == 'id' else 'by'} {by}"

def _metric_labels(deps: WorkflowDependencies) -> dict[str, str]:
    try:
        from app.ask_data.follow_up_suggestions import metric_labels

        return metric_labels(deps.semantic_context)
    except Exception:
        return {}


def _settled_follow_ups(
    analysis: AnalysisOutput, deps: WorkflowDependencies, *, asked: str, metric: str | None, dimensions: list[str] | None
) -> AnalysisOutput:
    """Keep only suggestions that can be answered when clicked; fill the rest from the model itself."""
    try:
        from app.ask_data.follow_up_suggestions import settle_follow_ups

        settled = settle_follow_ups(
            list(analysis.follow_up_questions or []),
            semantic_context=deps.semantic_context,
            asked=asked,
            metric=metric,
            dimensions=dimensions,
            language=detect_language(asked),
        )
    except Exception:
        logger.exception("follow_up_suggestions_failed")
        return analysis
    return analysis.model_copy(update={"follow_up_questions": settled})


def build_workflow(deps: WorkflowDependencies):
    def _turn_reading(state: AskDataState) -> TurnReading:
        existing = reading_from_state(state)
        if existing is not None:
            return existing
        return TurnReading(kind="data", standalone_question=str(state["question"]), rationale="workflow_default")

    async def understand_request(state: AskDataState) -> AskDataState:
        started = perf_counter()
        original_question = state.get("original_question") or state["question"]
        intent = _turn_reading(state)
        intent_payload = intent.model_dump()
        if intent.is_conversational:
            starters = state.get("capability_starter_questions")
            configured_starters = starters if isinstance(starters, list) and starters else None
            guidance = deps.semantic_context.guidance_context(
                original_question,
                configured_starters=configured_starters,
            )
            first_turn = not bool(state.get("conversation_history"))
            convo_prompt = "greeting.md"
            try:
                answer = await _provider(state, deps).generate_structured(
                    [
                        {"role": "system", "content": _ask_data_global_system() + "\n" + _prompt(convo_prompt)},
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "question": original_question,
                                    "first_turn": first_turn,
                                    "conversation_history": state.get("conversation_history", []),
                                    "capabilities": guidance,
                                    "metric_labels": _metric_labels(deps),
                                    "assistant_name": _assistant_name(deps),
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ],
                    AnalysisOutput,
                    temperature=0.4,
                    max_tokens=900,
                )
            except ProviderError:
                greet_id = detect_language(original_question) == "id"
                answer = AnalysisOutput(
                    direct_answer=(
                        f"Halo! Saya {_assistant_name(deps)}. Saya menjawab pertanyaan bisnis dari semantic model yang dipublish."
                        if greet_id
                        else f"Hello! I'm {_assistant_name(deps)}. I answer business questions from the published semantic model."
                    ),
                    executive_summary=(
                        "Tanyakan sebuah metrik, breakdown, atau perbandingan periode. Beberapa contoh ada di bawah."
                        if greet_id
                        else "Ask for a metric, a breakdown or a comparison between periods. A few examples are below."
                    ),
                    insights=[],
                    business_implications=[],
                    caveats=["Tidak ada query di turn ini." if greet_id else "No query ran on this turn."],
                    data_reference="Published semantic model capability catalog.",
                    chart_spec=None,
                )
            answer = _settled_follow_ups(answer, deps, asked=original_question, metric=None, dimensions=None)
            # No query ran: a data note saying so only adds noise under a greeting.
            answer = answer.model_copy(update={"caveats": [], "data_reference": ""})
            if intent.attach_domain_catalog:
                precomputed = guidance.get("domain_capability_lines")
                if isinstance(precomputed, list) and precomputed:
                    insight_lines = precomputed
                else:
                    insight_lines = deps.semantic_context.domain_capability_insight_lines(
                        language=detect_language(original_question),
                    )
                answer = answer.model_copy(update={"insights": insight_lines})
            return {
                **state,
                "turn_reading": intent_payload,
                "request_id": state.get("request_id") or str(uuid.uuid4()),
                "status": "SUCCESS",
                "strategy": "conversational",
                "answer": answer.model_dump(),
                "chart_spec": None,
                "query_result": {"columns": [], "rows": [], "row_count": 0, "execution_ms": 0},
                "timings": _with_timing(state, "context_ms", _elapsed(started)),
            }
        # ChatService resolves the (rewritten) question before the workflow starts.
        existing = state.get("semantic_resolution")
        if isinstance(existing, dict) and existing.get("status"):
            resolution = existing
        else:
            resolution = deps.semantic_context.resolve(
                state["question"],
                session_last_metric=state.get("session_last_metric"),
                session_analysis_context=state.get("session_analysis_context"),
            )
        update: AskDataState = {
            **state,
            "turn_reading": intent_payload,
            "request_id": state.get("request_id") or str(uuid.uuid4()),
            "semantic_resolution": resolution,
            "retry_count": state.get("retry_count", 0),
            "timings": _with_timing(state, "context_ms", _elapsed(started)),
        }
        if resolution.get("status") == "needs_clarification":
            update.update(
                status="CLARIFICATION",
                strategy="clarification",
                answer=_safe_answer(str(resolution.get("question") or "Please clarify the requested metric.")),
                chart_spec=None,
                query_result={"columns": [], "rows": [], "row_count": 0, "execution_ms": 0},
            )
            if resolution.get("context_mode"):
                update["context_mode"] = resolution.get("context_mode")
            return update
        if resolution.get("status") == "raw_table":
            update["raw_table_policy"] = resolution.get("raw_table_policy")
            update["context_mode"] = resolution.get("context_mode") or "RAW_TABLE"
            if isinstance(resolution.get("datasource_context"), dict):
                update["datasource_context"] = resolution.get("datasource_context")
            return update
        return update

    async def resolve_datasource(state: AskDataState) -> AskDataState:
        started = perf_counter()
        if state.get("status"):
            return state
        pre_resolution = state.get("semantic_resolution")
        if isinstance(pre_resolution, dict) and pre_resolution.get("status") == "raw_table":
            ds = pre_resolution.get("datasource_context")
            if isinstance(ds, dict):
                return {
                    **state,
                    "datasource_context": ds,
                    "raw_table_policy": pre_resolution.get("raw_table_policy"),
                    "context_mode": pre_resolution.get("context_mode") or "RAW_TABLE",
                    "timings": _with_timing(state, "datasource_ms", _elapsed(started)),
                }
        if deps.session_factory is None or deps.settings is None:
            return {
                **state,
                "datasource_context": {"legacy_fallback": True, "dialect": "hive"},
                "timings": _with_timing(state, "datasource_ms", _elapsed(started)),
            }
        resolution = state.get("semantic_resolution") or {}
        from app.ask_data.datasource_router import AskDataDatasourceRouter
        from app.ask_data.types import DatasourceExecutionContext, DatasourceRoutingError

        bundle_mode = str(state.get("runtime_mode") or "legacy")
        version_raw = state.get("semantic_version_id")
        semantic_version_id = uuid.UUID(str(version_raw)) if version_raw else None
        workspace_id = uuid.UUID(str(state["workspace_id"])) if state.get("workspace_id") else None
        project_id = uuid.UUID(str(state["project_id"])) if state.get("project_id") else None
        if workspace_id is None or project_id is None:
            from app.projects.resolver import load_default_project

            with deps.session_factory() as session:
                project = load_default_project(deps.settings)
            if project:
                workspace_id = project.workspace_id
                project_id = project.id
        if workspace_id is None or project_id is None:
            return {
                **state,
                "datasource_context": {"legacy_fallback": True, "dialect": "hive"},
                "timings": _with_timing(state, "datasource_ms", _elapsed(started)),
            }

        routing: DatasourceExecutionContext | DatasourceRoutingError
        with deps.session_factory() as session:
            router = AskDataDatasourceRouter(session, settings=deps.settings)
            if resolution.get("status") == "resolved":
                metric = str(resolution["metric"])
                definition = resolution.get("definition") or deps.semantic_context.metric_definition(metric)
                dataset_name = str(definition.get("base_dataset") or "")
                routing = router.resolve_for_governed_metric(
                    workspace_id=workspace_id,
                    project_id=project_id,
                    semantic_version_id=semantic_version_id,
                    dataset_name=dataset_name,
                    bundle_mode=bundle_mode,
                )
            else:
                routing = DatasourceExecutionContext(
                    legacy_fallback=True,
                    semantic_version_id=semantic_version_id,
                    dialect="hive",
                )

        update: AskDataState = {
            **state,
            "timings": _with_timing(state, "datasource_ms", _elapsed(started)),
        }
        if isinstance(routing, DatasourceRoutingError):
            answer = await explain_failure(
                provider=_provider(state, deps),
                question=state["question"],
                failure={"kind": "datasource", "code": routing.code, "detail": routing.message},
                request_id=str(state.get("request_id") or ""),
            )
            update.update(
                datasource_error=routing.to_dict(),
                status="ERROR",
                strategy="unsupported",
                answer=answer.model_dump(),
                chart_spec=None,
                query_result={"columns": [], "rows": [], "row_count": 0, "execution_ms": 0},
            )
            return update
        update["datasource_context"] = routing.to_dict()
        return update

    async def plan_query(state: AskDataState) -> AskDataState:
        started = perf_counter()
        resolution = state["semantic_resolution"]
        partial_caveats: list[str] = []
        attention_notes: list[str] = []
        drill_state: dict[str, Any] | None = None
        reference_sql = ""
        coverage_source: dict[str, str] = {}
        if resolution.get("status") == "raw_table":
            raw = resolution.get("raw_table") if isinstance(resolution.get("raw_table"), dict) else {}
            qualified = str(raw.get("qualified_name") or "")
            columns = list(raw.get("column_names") or [])
            from app.ask_data.types import DatasourceExecutionContext

            ds_ctx = DatasourceExecutionContext.from_dict(state.get("datasource_context"))
            dialect = ds_ctx.dialect if ds_ctx else "hive"
            raw_policy = state.get("raw_table_policy") if isinstance(state.get("raw_table_policy"), dict) else {}
            companion_tables = raw_policy.get("tables") if isinstance(raw_policy.get("tables"), list) else []
            allowed_tables = [
                str(entry.get("qualified_name"))
                for entry in companion_tables
                if isinstance(entry, dict) and entry.get("qualified_name")
            ]
            if not allowed_tables:
                allowed_tables = [qualified] if qualified else []
            rules = [
                "Use strategy sql_fallback with a single SELECT or WITH query.",
                "Do not use INSERT, UPDATE, DELETE, DDL, or multiple statements.",
            ]
            if len(allowed_tables) > 1:
                rules.append(
                    "You may JOIN only among these qualified tables: "
                    + ", ".join(allowed_tables)
                    + ". Use explicit column lists (no SELECT *)."
                )
            else:
                rules.append(f"Query only from {qualified} (alias d).")
            try:
                plan = await _provider(state, deps).generate_structured(
                    [
                        {"role": "system", "content": _ask_data_global_system() + "\n" + _prompt("query_planner.md")},
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "question": state["question"],
                                    "mode": "raw_table",
                                    "raw_table": {
                                        "qualified_name": qualified,
                                        "columns": columns,
                                        "dialect": dialect,
                                        "allowed_tables": allowed_tables,
                                    },
                                    "rules": rules,
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ],
                    QueryPlan,
                    temperature=0,
                    max_tokens=1800,
                )
            except ProviderError:
                plan = QueryPlan(
                    strategy="clarification",
                    clarification_question="Could not plan a safe query for the selected table.",
                )
            if plan.strategy != "sql_fallback" or not (plan.sql or "").strip():
                plan = QueryPlan(
                    strategy="clarification",
                    clarification_question=plan.clarification_question
                    or "Please clarify the aggregation, filters, and time range for this table.",
                )
            inquiry_brief = build_inquiry_brief(
                state["question"],
                semantic_resolution=resolution,
                query_plan=plan.model_dump(),
                session_last_metric=state.get("session_last_metric"),
            )
            update: AskDataState = {
                **state,
                "strategy": plan.strategy,
                "query_plan": plan.model_dump(),
                "sql": plan.sql or "",
                "governed_partial_caveats": [],
                "governed_entity_lookup": False,
                "semantic_context": {"raw_table": raw, "mode": "raw_table"},
                "inquiry_brief": inquiry_brief,
                "context_mode": resolution.get("context_mode") or "RAW_TABLE",
                "timings": _with_timing(state, "planning_ms", _elapsed(started)),
            }
            if plan.strategy == "clarification":
                text = plan.clarification_question or "Please clarify the requested analysis."
                update.update(
                    status="CLARIFICATION",
                    answer=_safe_answer(text),
                    chart_spec=None,
                    query_result={"columns": [], "rows": [], "row_count": 0, "execution_ms": 0},
                )
            return update
        if resolution.get("status") == "resolved" and isinstance(resolution.get("intent"), dict):
            # Understood by the language model (app.ask_data.understanding): the SQL is compiled from the checked intent, and
            # none of the wording-based readers below (comparisons, typo filters, yearless periods) runs.
            intent = resolution["intent"]
            metric = str(resolution["metric"])
            definition = resolution.get("definition") or deps.semantic_context.metric_definition(metric)
            dataset_name = str(definition.get("base_dataset") or "")
            from app.ask_data.types import DatasourceExecutionContext

            ds_ctx = DatasourceExecutionContext.from_dict(state.get("datasource_context"))
            from_source = ds_ctx.qualified_sources.get(dataset_name) if ds_ctx and ds_ctx.qualified_sources else None
            intent = await _top_groups_first(intent, metric, from_source, state, deps)
            resolution = {**resolution, "intent": intent}
            governed_sql = deps.semantic_context.compile_intent(metric, intent, from_source=from_source)
            plan = QueryPlan(strategy="governed", domains=[dataset_name], metrics=[metric], sql=governed_sql)
            if from_source:
                coverage_source = {"dataset": dataset_name, "source": from_source}
                if (intent.get("breakdown") or intent.get("time_key")) and definition.get("governance_status") != "reference":
                    reference_sql = deps.semantic_context.compile_intent(metric, intent, from_source=from_source, overall=True)
            indonesian = intent.get("language") == "id"
            partial_caveats = [str(n) for n in intent.get("notes") or []]
            if intent.get("filters"):
                from app.ask_data.column_labels import column_labels

                names = column_labels([str(f.get("dimension")) for f in intent["filters"]], semantic_context=deps.semantic_context)
                scope = "; ".join(f"{names.get(str(f.get('dimension'))) or f.get('dimension')}: {' or '.join(map(str, f.get('values') or []))}" for f in intent["filters"])
                partial_caveats.append(f"Difilter ke: {scope}." if indonesian else f"Filtered to: {scope}.")
        elif resolution.get("status") == "resolved":
            partial_caveats = _governed_partial_caveats(resolution, detect_language(state["question"]))
            metric = str(resolution["metric"])
            definition = resolution.get("definition") or deps.semantic_context.metric_definition(metric)
            dataset_name = str(definition.get("base_dataset") or "")
            allowed_dims = set(definition.get("allowed_dimensions") or [])
            dimensions = resolution.get("dimensions")
            extra_predicates: list[str] | None = None
            from app.ask_data.types import DatasourceExecutionContext

            ds_ctx = DatasourceExecutionContext.from_dict(state.get("datasource_context"))
            from_source = None
            if ds_ctx and ds_ctx.qualified_sources:
                from_source = ds_ctx.qualified_sources.get(dataset_name)
            if from_source and getattr(deps.semantic_context, "_registry_runtime", False):
                from app.ask_data.value_filters import resolve_value_matches

                value_resolution = await resolve_value_matches(
                    question=state["question"],
                    dataset_name=dataset_name,
                    metric_expression=str(definition.get("expression") or ""),
                    allowed_dimensions=allowed_dims,
                    from_source=from_source,
                    semantic_context=deps.semantic_context,
                    executor=deps.query_executor,
                    state=state,
                    breakdown_dimensions={str(d) for d in dimensions or []},
                    extra_words=[
                        metric,
                        *((definition.get("ai_context") or {}).get("synonyms") or []),
                        str((definition.get("ai_context") or {}).get("display_name") or ""),
                    ],
                )
                value_filters = value_resolution.filters
                indonesian = detect_language(state["question"]) == "id"
                if value_filters:
                    extra_predicates = [*(extra_predicates or []), *(f.predicate() for f in value_filters)]
                    from app.ask_data.column_labels import column_labels

                    names = column_labels([f.dimension for f in value_filters], semantic_context=deps.semantic_context)
                    scope = "; ".join(f.describe(names.get(f.dimension)) for f in value_filters)
                    partial_caveats = [*partial_caveats, f"Difilter ke: {scope}." if indonesian else f"Filtered to: {scope}."]
                for heard, value in value_resolution.corrections:
                    partial_caveats = [
                        *partial_caveats,
                        f"“{heard}” dibaca sebagai {value}." if indonesian else f"“{heard}” was read as {value}.",
                    ]
                for heard, candidates in value_resolution.suggestions:
                    options = " / ".join(candidates)
                    note = (
                        f"“{heard}” tidak dipakai sebagai filter karena belum pasti. Maksudnya {options}? Tulis nama lengkapnya agar hasilnya terfilter."
                        if indonesian
                        else f"“{heard}” was not used as a filter because it is not certain. Did you mean {options}? Spell it out to filter the result."
                    )
                    partial_caveats = [*partial_caveats, note]
                    attention_notes.append(note)
            from app.ask_data.intent_satisfaction import parse_yearless_period

            assumed_period = parse_yearless_period(state["question"])
            if assumed_period is not None:
                partial_caveats = [
                    *partial_caveats,
                    f"Tahun tidak disebut, jadi dipakai periode terbaru yang sudah selesai: {assumed_period.label}."
                    if detect_language(state["question"]) == "id"
                    else f"No year was given, so the most recent finished period is used: {assumed_period.label}.",
                ]
            if (
                ds_ctx
                and ds_ctx.qualified_sources
                and getattr(deps.semantic_context, "_registry_runtime", False)
            ):
                from app.ask_data.drill_across import plan_queries

                drilled = await plan_queries(
                    question=state["question"],
                    primary_metric=metric,
                    semantic_context=deps.semantic_context,
                    qualified_sources=dict(ds_ctx.qualified_sources),
                    executor=deps.query_executor,
                    state=state,
                )
                compared = None
                if not drilled:
                    from app.ask_data.comparisons import detect_benchmark, detect_period_comparison, plan_comparison
                    from app.ask_data.period_understanding import looks_like_period_comparison, reconcile, understand_periods

                    periods_hint = None
                    period_disagreement = False
                    if looks_like_period_comparison(state["question"]) and detect_benchmark(state["question"]) is None:
                        model_reading = await understand_periods(_provider(state, deps), state["question"])
                        periods_hint, period_disagreement = reconcile(detect_period_comparison(state["question"]), model_reading)
                    compared = await plan_comparison(
                        periods_hint=periods_hint,
                        question=state["question"],
                        primary_metric=metric,
                        semantic_context=deps.semantic_context,
                        qualified_sources=dict(ds_ctx.qualified_sources),
                        executor=deps.query_executor,
                        state=state,
                    )
                    if looks_like_period_comparison(state["question"]) and detect_benchmark(state["question"]) is None and not compared:
                        unread = (
                            "Dua periode yang ingin dibandingkan tidak terbaca otomatis, jadi hasil ini tidak dibandingkan per periode. Tulis dengan tahun, misalnya “Maret 2026 vs Juni 2026”."
                            if detect_language(state["question"]) == "id"
                            else "The two periods to compare could not be read, so this result is not compared by period. Write them with the year, for example “March 2026 vs June 2026”."
                        )
                        partial_caveats = [*partial_caveats, unread]
                        attention_notes.append(unread)
                if compared:
                    drill_state, scope_notes = compared
                    meta = drill_state["meta"]
                    is_id = detect_language(state["question"]) == "id"
                    if drill_state["kind"] == "periods":
                        explanation = (
                            f"Dua periode dibandingkan ({meta['previous']} dan {meta['current']}); tiap periode dihitung terpisah dari definisi governed-nya, perubahan = periode kemudian dikurangi periode awal."
                            if is_id
                            else f"Two periods are compared ({meta['previous']} and {meta['current']}); each is computed separately from the governed definition and the change is later minus earlier."
                        )
                    elif meta.get("direction") == "any":
                        explanation = (
                            "Nilai dibandingkan dengan nilai keseluruhan metrik (dihitung dari seluruh data); selisih = nilai kelompok dikurangi nilai keseluruhan."
                            if is_id
                            else "Compared with the overall value of the metric (computed over all records); difference = the group's value minus the overall value."
                        )
                    else:
                        side = ("di atas" if meta["direction"] == "above" else "di bawah") if is_id else meta["direction"]
                        by = f" lebih dari {meta['margin']:g} poin" if is_id and meta["margin"] else (f" by more than {meta['margin']:g} points" if meta["margin"] else "")
                        explanation = (
                            f"Dibandingkan dengan nilai keseluruhan metrik (dihitung dari seluruh data, bukan rata-rata kelompok); hanya kelompok {side} nilai itu{by}."
                            if is_id
                            else f"Compared with the overall value of the metric (computed over all records, not the average of the groups); only groups {side} it{by} are shown."
                        )
                    if drill_state["kind"] == "periods" and period_disagreement:
                        explanation += (
                            f" Pola teks membaca periode secara berbeda; yang dipakai: {meta['previous']} dan {meta['current']}."
                            if is_id
                            else f" The wording could be read two ways; the periods used are {meta['previous']} and {meta['current']}."
                        )
                    partial_caveats = [*[c for c in partial_caveats if not c.startswith(("Filtered to:", "Difilter ke:"))], explanation]
                    if scope_notes:
                        scope = "; ".join(scope_notes)
                        partial_caveats.append(f"Difilter ke: {scope}." if is_id else f"Filtered to: {scope}.")
                if drilled:
                    queries, scope_notes = drilled
                    drill_state = {
                        "queries": [
                            {"metric": q.metric, "sql": q.sql, "resolution": q.resolution, "dimensions": q.dimensions}
                            for q in queries
                        ],
                        "columns": {("metric_value" if i == 0 else q.metric): q.metric for i, q in enumerate(queries)},
                    }
                    partial_caveats = [
                        *[c for c in partial_caveats if not c.startswith(("Filtered to:", "Difilter ke:"))],
                        (
                            "Setiap metrik dihitung terpisah dari definisi governed-nya lalu digabung pada nilai dimensi yang sama."
                            if detect_language(state["question"]) == "id"
                            else "Each metric is computed separately from its governed definition and joined on the shared dimension values."
                        ),
                    ]
                    if scope_notes:
                        scope = "; ".join(scope_notes)
                        partial_caveats.append(
                            f"Difilter ke: {scope}." if detect_language(state["question"]) == "id" else f"Filtered to: {scope}."
                        )
            governed_sql = (
                deps.semantic_context.compile_governed(
                    metric,
                    state["question"],
                    dimensions,
                    extra_predicates=extra_predicates,
                    from_source=from_source,
                )
                if dimensions is not None
                else deps.semantic_context.compile_governed(
                    metric,
                    state["question"],
                    extra_predicates=extra_predicates,
                    from_source=from_source,
                )
            )
            plan = QueryPlan(
                strategy="governed",
                domains=sorted({definition.get("base_dataset") or dataset_name, *(
                    q["resolution"]["definition"].get("base_dataset") for q in (drill_state or {}).get("queries", [])
                )}),
                metrics=[q["metric"] for q in drill_state["queries"]] if drill_state else [metric],
                sql=drill_state["queries"][0]["sql"] if drill_state else governed_sql,
            )
            if from_source:
                coverage_source = {"dataset": dataset_name, "source": from_source}
            if not drill_state and dimensions and from_source and definition.get("governance_status") != "reference":
                # The same metric, filters and period without the breakdown: the overall value the groups are read against.
                try:
                    reference_sql = deps.semantic_context.compile_governed(
                        metric, state["question"], [], extra_predicates=extra_predicates, from_source=from_source
                    )
                except Exception:  # noqa: BLE001 - context only
                    logger.warning("overall_value_compile_failed metric=%s", metric)
                    reference_sql = ""
            if getattr(deps.semantic_context, "_registry_runtime", False):
                from app.ask_data.intent_satisfaction import validate_governed_sql_covers_intent

                sql_check = validate_governed_sql_covers_intent(
                    state["question"],
                    governed_sql,
                    definition={**definition, "metric": metric},
                    registry=deps.semantic_context.registry,
                )
                if not sql_check.intent_complete:
                    plan = QueryPlan(
                        strategy="clarification",
                        clarification_question=sql_check.user_message
                        or "The question could not be mapped to a complete governed query.",
                    )
                    resolution = {
                        **resolution,
                        "intent_validation": sql_check.as_metadata(),
                    }
        else:
            semantic_context = deps.semantic_context.planner_context()
            # Resolved metrics (including partial dimension coverage) always
            # take the governed compile path above. Hints here are only for
            # fallback/multi_concept cases where the planner must choose.
            resolver_hint: dict[str, Any] = {}
            if resolution.get("status") == "fallback" and resolution.get("reason") == "multi_concept_metric_mismatch":
                resolver_hint = {
                    "requested_concepts": resolution.get("requested_concepts"),
                    "candidate_metric_for_one_concept": resolution.get("candidate_metric"),
                    "note": "The question asks about multiple distinct concepts that no single governed metric covers together. Check semantic_context.metrics for a separate governed metric per concept and use sql_fallback to combine them if each concept has its own approved metric/view, or governed per metric in sequence - do not choose unsupported just because one metric can't cover every concept at once.",
                }
            if resolution.get("status") == "unsupported":
                plan = QueryPlan(
                    strategy="clarification",
                    clarification_question=str(
                        resolution.get("question")
                        or (
                            "Mohon jelaskan domain, metrik, periode, dan breakdown yang dibutuhkan."
                            if detect_language(str(state.get("question") or "")) == "id"
                            else "Please specify the metric, period and breakdown you need."
                        )
                    ),
                )
            else:
                try:
                    plan = await _provider(state, deps).generate_structured(
                        [
                            {"role": "system", "content": _ask_data_global_system() + "\n" + _prompt("query_planner.md")},
                            {
                                "role": "user",
                                "content": json.dumps(
                                    {
                                        "question": state["question"],
                                        "semantic_context": semantic_context,
                                        "resolver_hint": resolver_hint or None,
                                    },
                                    ensure_ascii=False,
                                ),
                            },
                        ],
                        QueryPlan,
                        temperature=0,
                        max_tokens=1800,
                    )
                except ProviderError:
                    logger.warning(
                        "plan_query_invalid_structured_output request_id=%s resolver=%s",
                        state.get("request_id"),
                        resolution.get("status"),
                    )
                    plan = QueryPlan(
                        strategy="clarification",
                        clarification_question=str(
                            resolution.get("question")
                            or (
                                "Pertanyaan belum terpetakan ke KPI governed. Sebutkan metrik, cabang/material, dan periode secara eksplisit."
                                if detect_language(str(state.get("question") or "")) == "id"
                                else "The question is not mapped to a governed KPI yet. Please name the metric, the breakdown and the period."
                            )
                        ),
                    )
        inquiry_brief = build_inquiry_brief(
            state["question"],
            semantic_resolution=resolution,
            query_plan=plan.model_dump(),
            session_last_metric=state.get("session_last_metric"),
        )
        update: AskDataState = {
            **state,
            "strategy": plan.strategy,
            "query_plan": plan.model_dump(),
            "sql": plan.sql or "",
            "governed_partial_caveats": partial_caveats,
                "attention_notes": attention_notes,
            "drill_across": drill_state or {},
            "reference_sql": reference_sql,
            "coverage_source": coverage_source,
            "semantic_context": deps.semantic_context.planner_context(plan.domains),
            "inquiry_brief": inquiry_brief,
            "judge_iteration": state.get("judge_iteration", 0),
            "judge_retry_plan": False,
            "judge_plan_hint": "",
            "timings": _with_timing(state, "planning_ms", _elapsed(started)),
        }
        if plan.strategy == "clarification":
            text = plan.clarification_question or "Please clarify the requested metric."
            update.update(status="CLARIFICATION", answer=_safe_answer(text), chart_spec=None, query_result={"columns": [], "rows": [], "row_count": 0, "execution_ms": 0})
        elif plan.strategy == "unsupported":
            update.update(status="UNSUPPORTED", answer=_safe_answer(
                "Data yang diminta tidak tersedia pada cakupan governed saat ini."
                if detect_language(str(state.get("question") or "")) == "id"
                else "The requested data is not available in the current governed scope."
            ), chart_spec=None, query_result={"columns": [], "rows": [], "row_count": 0, "execution_ms": 0})
        return update

    async def validate_query(state: AskDataState) -> AskDataState:
        started = perf_counter()
        result = deps.sql_validator(state.get("sql", ""), state)
        retry_count = state.get("retry_count", 0)
        if not result.valid:
            logger.warning(
                "sql_validation_failed request_id=%s error=%s sql=%s",
                state.get("request_id"),
                result.error,
                str(state.get("sql") or "")[:400],
            )
        if not result.valid and retry_count < 1:
            try:
                repair = await _provider(state, deps).generate_structured(
                    [
                        {"role": "system", "content": _ask_data_global_system() + "\n" + _prompt("sql_repair.md")},
                        {"role": "user", "content": json.dumps({"invalid_sql": state.get("sql"), "error": result.error, "semantic_context": state.get("semantic_context")}, ensure_ascii=False)},
                    ],
                    QueryPlan,
                    temperature=0,
                    max_tokens=1200,
                )
            except ProviderError:
                # A malformed repair must not hide the real validation error behind a generic failure.
                logger.warning("sql_repair_failed request_id=%s", state.get("request_id"))
                repair = None
            retry_count += 1
            if repair is not None:
                result = deps.sql_validator(repair.sql or "", state)
                state = {**state, "query_plan": repair.model_dump(), "sql": repair.sql or ""}
        drill = state.get("drill_across") or {}
        if result.valid and drill.get("queries"):
            checked = []
            for extra in drill["queries"][1:]:
                check = deps.sql_validator(extra["sql"], {**state, "semantic_resolution": extra["resolution"]})
                if not check.valid:
                    logger.warning(
                        "drill_across_sql_invalid request_id=%s metric=%s error=%s",
                        state.get("request_id"),
                        extra.get("metric"),
                        check.error,
                    )
                    result = check
                    break
                checked.append({**extra, "sql": check.sql or extra["sql"]})
            else:
                state = {**state, "drill_across": {**drill, "queries": [drill["queries"][0], *checked]}}
        if result.valid and state.get("reference_sql"):
            resolution_now = state.get("semantic_resolution") if isinstance(state.get("semantic_resolution"), dict) else {}
            check = deps.sql_validator(state["reference_sql"], {**state, "semantic_resolution": {**resolution_now, "dimensions": []}})
            state = {**state, "reference_sql": (check.sql or state["reference_sql"]) if check.valid else ""}
        update: AskDataState = {
            **state,
            "retry_count": retry_count,
            "validation_error": result.error or "",
            "timings": _with_timing(state, "validation_ms", _elapsed(started)),
        }
        if result.valid:
            update["validated_sql"] = result.sql or ""
        else:
            error_answer = await explain_failure(
                provider=_provider(state, deps),
                question=state["question"],
                failure={
                    "kind": "sql_validation",
                    "code": "INVALID_SQL",
                    "detail": result.error or "",
                },
                request_id=str(state.get("request_id") or ""),
            )
            update.update(
                status="ERROR",
                answer=error_answer.model_dump(),
                chart_spec=None,
                query_result={"columns": [], "rows": [], "row_count": 0, "execution_ms": 0},
            )
        return update

    async def execute_query(state: AskDataState) -> AskDataState:
        started = perf_counter()
        try:
            result = deps.query_executor.execute(state["validated_sql"], state)
            if inspect.isawaitable(result):
                result = await result
            drill = state.get("drill_across") or {}
            if drill.get("queries") and len(drill["queries"]) > 1:
                from app.ask_data.comparisons import merge_drill_results

                results = [result]
                for extra in drill["queries"][1:]:
                    more = deps.query_executor.execute(extra["sql"], state)
                    if inspect.isawaitable(more):
                        more = await more
                    results.append(more)
                result = merge_drill_results(drill, results)
        except Exception as exc:
            from app.connectors.errors import ConnectorError

            if not isinstance(exc, ConnectorError):
                raise
            answer = await explain_failure(
                provider=_provider(state, deps),
                question=state["question"],
                failure={"kind": "datasource", "code": exc.code, "detail": exc.message},
                request_id=str(state.get("request_id") or ""),
            )
            from app.core.config import get_settings

            if get_settings().ask_data_show_query_errors:
                shown_sql = " ".join(str(state.get("validated_sql") or "").split())[:900]
                answer = answer.model_copy(
                    update={
                        "caveats": [
                            *answer.caveats,
                            f"Data source message: {' '.join(str(exc.message).split())[:300]}",
                            *([f"SQL: {shown_sql}"] if shown_sql else []),
                        ]
                    }
                )
            return {
                **state,
                "status": "ERROR",
                "answer": answer.model_dump(),
                "chart_spec": None,
                "query_result": {"columns": [], "rows": [], "row_count": 0, "execution_ms": 0},
                "timings": _with_timing(state, "query_ms", _elapsed(started)),
            }
        update: AskDataState = {
            **state,
            "query_result": result,
            "timings": _with_timing(state, "query_ms", _elapsed(started)),
        }
        rows = result.get("rows") or []
        from app.ask_data import answer_context

        coverage_source = state.get("coverage_source") or {}
        if coverage_source.get("source") and getattr(deps.semantic_context, "registry", None) is not None:
            update["data_coverage"] = await answer_context.data_coverage(
                executor=deps.query_executor,
                state=state,
                dataset=coverage_source.get("dataset", ""),
                source=coverage_source["source"],
                registry=deps.semantic_context.registry,
            )
        if len(rows) > 1 and state.get("reference_sql"):
            update["overall_value"] = await answer_context.overall_value(
                executor=deps.query_executor, state=state, sql=state["reference_sql"]
            )
        # COUNT over a period the data does not hold returns one row of 0: that is no data, not a zero.
        outside = answer_context.period_outside_coverage(str(state.get("question") or ""), update.get("data_coverage"))
        only_zeros = bool(rows) and all(
            value in (0, None) for row in rows for key, value in row.items() if str(key).startswith("metric_value")
        )
        if not rows or (outside and only_zeros):
            if rows:
                update["query_result"] = {**result, "rows": [], "row_count": 0}
            language = detect_language(state.get("original_question") or state["question"])
            message = answer_context.no_data_message(str(state.get("question") or ""), update.get("data_coverage"), language)
            update.update(
                status="NO_DATA",
                answer=_safe_answer(
                    message
                    or (
                        "Tidak ada data yang cocok untuk pertanyaan dan filter tersebut."
                        if language == "id"
                        else "No data matches this question and these filters."
                    )
                ),
                chart_spec=None,
            )
        return update

    async def analyze_result(state: AskDataState) -> AskDataState:
        started = perf_counter()
        resolution = state.get("semantic_resolution") if isinstance(state.get("semantic_resolution"), dict) else {}
        if state.get("strategy") in ("governed", "sql_fallback") and isinstance(state.get("query_result"), dict):
            from app.ask_data.verification import verify_answer, warning_messages

            result_for_check = state["query_result"]
            checks = verify_answer(
                question=str(state.get("question") or ""),
                sql=str(state.get("validated_sql") or state.get("sql") or ""),
                columns=list(result_for_check.get("columns") or []),
                rows=list(result_for_check.get("rows") or []),
                definition=resolution.get("definition") if isinstance(resolution.get("definition"), dict) else None,
                drill=state.get("drill_across") if isinstance(state.get("drill_across"), dict) else None,
                truncated=bool(result_for_check.get("truncated")),
            )
            from app.core.models import CalculationCheck

            checks = [
                *checks,
                *[CalculationCheck(name="attention", status="warning", message=m) for m in (state.get("attention_notes") or [])],
            ]
            known = list(state.get("governed_partial_caveats") or [])
            state = {
                **state,
                "verification_checks": [check.model_dump() for check in checks],
                "governed_partial_caveats": [*known, *[m for m in warning_messages(checks) if m not in known]],
            }
        user_payload: dict[str, Any] = {
            "question": state["question"],
            "query_plan": state.get("query_plan"),
            "semantic_context": state.get("semantic_context"),
            "query_result": state["query_result"],
            "inquiry_brief": state.get("inquiry_brief"),
            "governed_metric": resolution.get("metric"),
            "governed_partial_caveats": state.get("governed_partial_caveats") or [],
            "metric_labels": _metric_labels(deps),
        }
        from app.ask_data import answer_context

        language = detect_language(str(state.get("original_question") or state.get("question") or ""))
        if state.get("overall_value") is not None:
            user_payload["overall_value"] = {
                "value": state["overall_value"],
                "meaning": "the same metric over the same filters and period, without the breakdown",
            }
        from app.ask_data.answer_checks import computed_figures, is_additive

        computed = computed_figures(
            list((state.get("query_result") or {}).get("rows") or []),
            _overall_figures(state.get("overall_value"))[0] if _overall_figures(state.get("overall_value")) else None,
            additive=is_additive(resolution.get("definition") if isinstance(resolution.get("definition"), dict) else None),
        )
        if computed:
            user_payload["computed"] = computed
        coverage_text = answer_context.coverage_label(state.get("data_coverage"), language)
        if coverage_text and answer_context.asks_about_time(str(state.get("original_question") or state.get("question") or "")):
            user_payload["data_coverage"] = coverage_text
        outside = answer_context.outside_caveat(str(state.get("question") or ""), state.get("data_coverage"), language)
        if outside:
            known = list(state.get("governed_partial_caveats") or [])
            if outside not in known:
                state = {**state, "governed_partial_caveats": [*known, outside]}
                user_payload["governed_partial_caveats"] = state["governed_partial_caveats"]
        if (state.get("drill_across") or {}).get("columns"):
            user_payload["result_columns_are_metrics"] = state["drill_across"]["columns"]
        if (state.get("drill_across") or {}).get("kind"):
            drill_info = state["drill_across"]
            user_payload["comparison"] = {"kind": drill_info["kind"], **(drill_info.get("meta") or {})}
        if state.get("judge_synthesis_hint"):
            user_payload["reviewer_hint"] = state["judge_synthesis_hint"]
        if state.get("ask_data_space_instructions"):
            user_payload["space_instructions"] = state["ask_data_space_instructions"]
        from app.prompt_management.keys import ASK_DATA_ANALYST
        from app.prompt_management.managed import managed_prompt

        analyst_prompt = managed_prompt(ASK_DATA_ANALYST, "result_analyst.md")
        analysis = None
        for attempt in range(2):
            try:
                analysis = await _provider(state, deps).generate_structured(
                    [
                        {"role": "system", "content": _ask_data_global_system() + "\n" + analyst_prompt},
                        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, default=str)},
                    ],
                    AnalysisOutput,
                    temperature=0.1,
                    max_tokens=2800,
                )
                break
            except ProviderError as exc:
                logger.warning(
                    "analyze_result_failed request_id=%s attempt=%s code=%s",
                    state.get("request_id"),
                    attempt + 1,
                    getattr(exc, "code", type(exc).__name__),
                )
                if attempt == 0:
                    await asyncio.sleep(2.0)
                    continue
        if analysis is None:
            rows = state.get("query_result", {}).get("rows") or []
            if rows:
                row_count = len(rows)
                caveat = (
                    "Ringkasan narasi otomatis: model analisis gagal merespons, "
                    "tetapi angka di bawah valid dari query governed."
                    if detect_language(str(state.get("question") or "")) == "id"
                    else "Automatic summary: the analysis model did not respond, "
                    "but the numbers below come from the governed query."
                )
                question_text = str(state.get("question") or "")
                direct = None
                deterministic_narrative = False
                if not direct:
                    from app.services.rows_summary import summarize_rows

                    direct = summarize_rows(rows, language=detect_language(question_text))
                if not direct:
                    plural = "" if row_count == 1 else "s"
                    direct = (
                        f"Query governed selesai dengan {row_count} baris hasil. Gunakan tabel di bawah untuk melihat hasilnya."
                        if detect_language(question_text) == "id"
                        else f"The governed query returned {row_count} row{plural}. Use the table below to see the result."
                    )
                answer_caveats = [] if deterministic_narrative else [caveat]
                return {
                    **state,
                    "status": "SUCCESS",
                    "answer": _safe_answer(direct, caveats=answer_caveats),
                    "chart_spec": state.get("chart_spec"),
                    "timings": _with_timing(state, "analysis_ms", _elapsed(started)),
                }
            error_answer = await explain_failure(
                provider=_provider(state, deps),
                question=state["question"],
                failure={"kind": "provider", "code": "ANALYSIS_OUTPUT"},
                request_id=str(state.get("request_id") or ""),
            )
            return {
                **state,
                "status": "ERROR",
                "answer": error_answer.model_dump(),
                "chart_spec": None,
                "timings": _with_timing(state, "analysis_ms", _elapsed(started)),
            }
        from app.ask_data.chart_inference import infer_chart_spec_from_result, repair_chart_spec

        columns_list = list(state["query_result"].get("columns") or [])
        columns = set(columns_list)
        rows = state["query_result"].get("rows") or []
        chart = analysis.chart_spec
        chart = repair_chart_spec(chart, columns=columns_list, rows=rows)
        if chart is None and rows:
            chart = infer_chart_spec_from_result(
                columns=columns_list,
                rows=rows,
                title=(analysis.chart_spec.title if analysis.chart_spec else None)
                or str(state.get("question") or "")[:80],
                question=str(state.get("question") or ""),
            )
        if chart and any(field and field not in columns for field in (chart.x, chart.y, chart.series)):
            chart = repair_chart_spec(chart, columns=columns_list, rows=rows)
        if chart and any(field and field not in columns for field in (chart.x, chart.y, chart.series)):
            chart = None
        if chart is not None and _title_is_the_question(chart.title, str(state.get("question") or ""), str(state.get("original_question") or "")):
            # A chart (or KPI) named after the question reads "bisa bantu keluarkan ...?: 16,34"; name it after the metric.
            label = _metric_labels(deps).get(str(resolution.get("metric") or ""))
            if label and chart.type != "kpi" and chart.x:
                from app.ask_data.column_labels import column_labels

                by = column_labels([chart.x], semantic_context=deps.semantic_context, sql=str(state.get("validated_sql") or "")).get(chart.x)
                label = _titled(label, by, str(state.get("original_question") or state.get("question") or ""))
            if label:
                chart = chart.model_copy(update={"title": label})
        if chart is not None:
            analysis = analysis.model_copy(update={"chart_spec": chart})
        elif analysis.chart_spec is not None:
            analysis = analysis.model_copy(update={"chart_spec": None})
        # Always override data_reference with just the view name(s) parsed
        # from the executed SQL - never trust the model to keep the raw
        # SQL text out of a field meant to be a plain-language citation,
        # regardless of what result_analyst.md asks for.
        schema_reference = _data_reference_from_sql(state.get("validated_sql") or state.get("sql") or "")
        if schema_reference:
            analysis = analysis.model_copy(update={"data_reference": schema_reference})
        extra = list(state.get("governed_partial_caveats") or [])
        if extra:
            merged = list(analysis.caveats)
            for item in extra:
                if item not in merged:
                    merged.append(item)
            analysis = analysis.model_copy(update={"caveats": merged})
        from app.ask_data.answer_checks import review_answer

        analysis, figure_warnings = review_answer(
            analysis,
            rows=rows,
            question=str(state.get("question") or ""),
            language=detect_language(str(state.get("question") or "")),
            extra_figures=_overall_figures(state.get("overall_value")),
        )
        figure_checks = [{"name": "figures", "status": "warning", "message": w} for w in figure_warnings]
        analysis = _settled_follow_ups(
            analysis,
            deps,
            asked=str(state.get("question") or ""),
            metric=str(resolution.get("metric") or "") or None,
            dimensions=[str(d) for d in resolution.get("dimensions") or []],
        )
        return {
            **state,
            "status": "SUCCESS",
            "answer": analysis.model_dump(),
            "chart_spec": chart.model_dump() if chart else None,
            "verification_checks": [*(state.get("verification_checks") or []), *figure_checks],
            "timings": _with_timing(state, "analysis_ms", _elapsed(started)),
            "judge_retry_synthesize": False,
            "judge_synthesis_hint": "",
        }

    async def tool_result(state: AskDataState) -> AskDataState:
        """A query the agent asked for (tool query_metric): the rows with the same checks, caveats and chart as an answer, and no
        write-up, because the agent writes one report from all of its queries."""
        started = perf_counter()
        resolution = state.get("semantic_resolution") if isinstance(state.get("semantic_resolution"), dict) else {}
        result = state.get("query_result") or {}
        columns_list = list(result.get("columns") or [])
        rows = list(result.get("rows") or [])
        from app.ask_data.verification import verify_answer, warning_messages
        from app.core.models import CalculationCheck

        checks = verify_answer(
            question=str(state.get("question") or ""),
            sql=str(state.get("validated_sql") or state.get("sql") or ""),
            columns=columns_list,
            rows=rows,
            definition=resolution.get("definition") if isinstance(resolution.get("definition"), dict) else None,
            drill=None,
            truncated=bool(result.get("truncated")),
        )
        checks = [*checks, *[CalculationCheck(name="attention", status="warning", message=m) for m in (state.get("attention_notes") or [])]]
        caveats = list(dict.fromkeys([*(state.get("governed_partial_caveats") or []), *warning_messages(checks)]))
        chart = None
        if len(rows) > 1:
            from app.ask_data.chart_inference import infer_chart_spec_from_result
            from app.ask_data.column_labels import column_labels

            label = _metric_labels(deps).get(str(resolution.get("metric") or "")) or str(state.get("question") or "")[:80]
            dims = [str(d) for d in resolution.get("dimensions") or []]
            by = column_labels(dims[-1:], semantic_context=deps.semantic_context, sql=str(state.get("validated_sql") or "")).get(dims[-1]) if dims else None
            chart = infer_chart_spec_from_result(columns=columns_list, rows=rows, title=_titled(label, by, str(state.get("original_question") or state.get("question") or "")), question=str(state.get("question") or ""))
        answer = AnalysisOutput(
            direct_answer="",
            executive_summary="",
            insights=[],
            business_implications=[],
            caveats=caveats,
            data_reference=_data_reference_from_sql(str(state.get("validated_sql") or "")) or "",
        )
        return {
            **state,
            "status": "SUCCESS",
            "answer": answer.model_dump(),
            "chart_spec": chart.model_dump() if chart else None,
            "verification_checks": [c.model_dump() for c in checks],
            "timings": _with_timing(state, "analysis_ms", _elapsed(started)),
        }

    async def judge_answer(state: AskDataState) -> AskDataState:
        if not deps.judge_enabled:
            return state
        if state.get("strategy") not in ("governed", "sql_fallback") or state.get("status") != "SUCCESS":
            return state
        review = judge_review(state, max_iterations=deps.judge_max_iterations)
        if review.get("accept"):
            return {**state, "judge_review": review, "judge_issues": []}
        replan = apply_judge_replan(state, review)
        answer = dict(state.get("answer") or {})
        if not review.get("retry_allowed"):
            caveats = list(answer.get("caveats") or [])
            note = "Reviewer: " + "; ".join(review.get("issues") or [])[:400]
            if note not in caveats:
                caveats.append(note)
            answer["caveats"] = caveats
            return {**state, **replan, "answer": answer, "judge_review": review}
        return {**state, **replan, "judge_review": review}

    def after_judge(state: AskDataState) -> str:
        review = state.get("judge_review") or {}
        if review.get("accept"):
            return "end"
        if state.get("judge_retry_plan") and review.get("retry_allowed"):
            return "plan_query"
        if state.get("judge_retry_synthesize"):
            return "analyze_result"
        return "end"

    def after_understand(state: AskDataState) -> str:
        return "end" if state.get("status") else "resolve_datasource"

    def after_resolve_datasource(state: AskDataState) -> str:
        return "end" if state.get("status") else "plan_query"

    def after_plan(state: AskDataState) -> str:
        return "end" if state.get("status") else "validate_query"

    def after_validate(state: AskDataState) -> str:
        return "end" if state.get("status") else "execute_query"

    def after_execute(state: AskDataState) -> str:
        if state.get("status"):
            return "end"
        return "tool_result" if state.get("tool_call") else "analyze_result"

    graph = StateGraph(AskDataState)
    graph.add_node("understand_request", understand_request)
    graph.add_node("resolve_datasource", resolve_datasource)
    graph.add_node("plan_query", plan_query)
    graph.add_node("validate_query", validate_query)
    graph.add_node("execute_query", execute_query)
    graph.add_node("analyze_result", analyze_result)
    graph.add_node("judge_answer", judge_answer)
    graph.add_edge(START, "understand_request")
    graph.add_conditional_edges(
        "understand_request",
        after_understand,
        {"resolve_datasource": "resolve_datasource", "end": END},
    )
    graph.add_conditional_edges(
        "resolve_datasource",
        after_resolve_datasource,
        {"plan_query": "plan_query", "end": END},
    )
    graph.add_conditional_edges("plan_query", after_plan, {"validate_query": "validate_query", "end": END})
    graph.add_conditional_edges("validate_query", after_validate, {"execute_query": "execute_query", "end": END})
    graph.add_node("tool_result", tool_result)
    graph.add_conditional_edges("execute_query", after_execute, {"analyze_result": "analyze_result", "tool_result": "tool_result", "end": END})
    graph.add_edge("tool_result", END)
    graph.add_edge("analyze_result", "judge_answer")
    graph.add_conditional_edges(
        "judge_answer",
        after_judge,
        {"plan_query": "plan_query", "analyze_result": "analyze_result", "end": END},
    )
    return graph.compile()
