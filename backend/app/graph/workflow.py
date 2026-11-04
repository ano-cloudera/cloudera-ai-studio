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
from app.graph.governed_replan import rank_dimensions_for_brief
from app.graph.judge_replan import apply_judge_replan
from app.graph.state import AskDataState
from app.semantic.context import is_governed_entity_lookup
from app.llm.base import LLMProvider, ProviderError
from app.services.conversational import TurnUnderstanding, turn_understanding_from_state
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
    # Optional: only used when our own planner reports strategy=unsupported.
    # None (the default in every existing test/deployment) skips the
    # fallback node entirely with no behavior change.
    local_agent_client: Any = None
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


def _row_from_follow_up_catalog(entity: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(entity, dict) or not entity.get("id"):
        return None
    dim = str(entity.get("entity_type") or entity.get("dimension") or "branch")
    row: dict[str, Any] = {dim: entity["id"]}
    if entity.get("metric_value") is not None:
        row["metric_value"] = entity["metric_value"]
    return row


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


_UNMET_DIMENSION_LABELS: dict[str, str] = {
    "branch": "branch / partner DC",
    "sales_off": "sales office",
    "sales_office": "sales office",
    "customer": "customer",
    "material": "material / product / SKU",
    "material_code": "material code",
    "dcname": "partner DC name",
    "e_store": "outlet / e-store",
    "plu": "PLU",
    "kode_plu": "PLU code",
    "division": "division",
    "cust_id": "store / outlet (customer id)",
    "cust_code": "customer code",
}


def _governed_partial_caveats(resolution: dict[str, Any], language: str = "en") -> list[str]:
    unmet = list(resolution.get("dimension_mismatch") or [])
    if not unmet:
        return []
    metric = str(resolution.get("metric") or "")
    labels = [_UNMET_DIMENSION_LABELS.get(name, name) for name in unmet]
    if language == "id":
        caveats = [
            f"Permintaan breakdown per {' dan '.join(labels)} tidak tersedia pada metrik yang dipilih ({metric}) "
            "dalam katalog governed. Angka di bawah hanya mencakup grain yang didukung metrik ini."
        ]
    else:
        caveats = [
            f"A breakdown by {' and '.join(labels)} is not available for the selected metric ({metric}) "
            "in the governed catalog. The figures below only cover the grain this metric supports."
        ]
    if metric == "months_of_stock_cover":
        caveats.append(
            "This stock cover is a proxy of warehouse stock against sell-in per material "
            "(in months, October to December 2024), not partner DC or outlet stock "
            "per branch and not a daily duration."
        )
    return caveats


def _partner_scope_caveats(question: str, resolution: dict[str, Any]) -> list[str]:
    lowered = (question or "").casefold()
    metric = str(resolution.get("metric") or "")
    b2b_metric = metric.startswith("b2b_") or "sell_out" in metric or "branch_sell_out" in metric
    b2b_wording = any(
        term in lowered for term in ("acme", "b2b", "sell-out", "sell out", "partner", "dc acme")
    )
    if not b2b_metric and not b2b_wording:
        return []
    return [
        "Domain note: Acme/B2B in Q4 2024 means partner-network sell-out; "
        "branch/DC is the value of the branch column (for example DC Palembang), not a branch='Acme' filter."
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


def _local_agent_second_enabled(deps: WorkflowDependencies) -> bool:
    client = deps.local_agent_client
    return client is not None and getattr(client, "enabled", False)


def _should_try_local_agent_second(state: AskDataState, deps: WorkflowDependencies) -> bool:
    """Primary path first; when LOCAL_AGENT_BASE_URL is set, consult Irvan's
    catalog before showing clarification/unsupported to the user."""
    if state.get("use_local_agent"):
        return True
    return _local_agent_second_enabled(deps)


async def _try_local_agent_fallback(state: AskDataState, deps: WorkflowDependencies) -> dict[str, Any] | None:
    """Second-option consult to REFERENCE Local Agent after our primary path
    could not produce a direct answer (unsupported, or selected clarifications).

    Returns an
    AnalysisOutput dict on success, or None on ANY failure (disabled,
    network error, timeout, the local agent itself refusing) - callers
    must treat None as "fall through to the existing unsupported
    message", never as a request-level failure. This function must never
    raise past its own try/except; a broken or unreachable fallback
    service must not turn a normal "unsupported" answer into a 500.
    """
    client = deps.local_agent_client
    if client is None or not getattr(client, "enabled", False):
        return None
    try:
        question = state.get("original_question") or state["question"]
        payload = await client.query(question, answer_language="id")
    except Exception as exc:  # noqa: BLE001 - any failure here must degrade to None, not propagate
        logger.info("local_agent_fallback_failed request_id=%s reason=%s", state.get("request_id"), type(exc).__name__)
        return None

    from app.services.local_agent_client import markdown_to_plain_answer

    markdown = str(payload.get("final_response_markdown") or "")
    text = markdown_to_plain_answer(markdown)
    if not text:
        return None
    query_ids = payload.get("resolved_query_ids") or []
    reference = f"REFERENCE Local Agent (separate governed catalog) - query: {', '.join(query_ids)}" if query_ids else "REFERENCE Local Agent (separate governed catalog)."
    return AnalysisOutput(
        direct_answer=text,
        executive_summary=text,
        insights=[],
        business_implications=[],
        caveats=[
            "This answer comes from a separate governed system (local agent), "
            "not from the main metric catalog, so its definitions or scope may differ slightly. "
            "Treat it as exploratory."
        ],
        data_reference=reference,
        chart_spec=None,
    ).model_dump()


def build_workflow(deps: WorkflowDependencies):
    async def _conversational_intent(state: AskDataState):
        existing = turn_understanding_from_state(state)
        if existing is not None:
            return existing
        original_question = str(state.get("original_question") or state["question"]).strip()
        return TurnUnderstanding(
            is_conversational=False,
            attach_domain_catalog=False,
            pipeline_question=original_question,
            rationale="workflow_default_analytic",
        )

    async def understand_request(state: AskDataState) -> AskDataState:
        started = perf_counter()
        original_question = state.get("original_question") or state["question"]
        intent = await _conversational_intent(state)
        intent_payload = intent.model_dump()
        if intent.is_conversational:
            starters = state.get("capability_starter_questions")
            configured_starters = starters if isinstance(starters, list) and starters else None
            guidance = deps.semantic_context.guidance_context(
                original_question,
                session_last_metric=state.get("session_last_metric"),
                session_capability_hint=state.get("session_capability_hint"),
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
                from app.services.conversational_fallback import (
                    deterministic_capability_overview_answer,
                )

                if intent.rationale in ("capability_overview", "capability_follow_up"):
                    from app.services.conversational_fallback import (
                        deterministic_capability_follow_up_answer,
                    )

                    excluded = guidance.get("excluded_focus")
                    hint = guidance.get("session_capability_hint")
                    if isinstance(hint, dict) and intent.rationale == "capability_follow_up":
                        answer = AnalysisOutput.model_validate(
                            deterministic_capability_follow_up_answer(
                                excluded_focus=excluded if isinstance(excluded, str) else None,
                                session_hint=hint,
                                language=detect_language(original_question),
                            )
                        )
                    else:
                        answer = AnalysisOutput.model_validate(
                            deterministic_capability_overview_answer(detect_language(original_question))
                        )
                else:
                    greet_id = detect_language(original_question) == "id"
                    answer = AnalysisOutput(
                        direct_answer=(
                            "Halo! Saya asisten Ask Data Cloudera AI Studio."
                            if greet_id
                            else "Hello! I'm the Ask Data assistant for Cloudera AI Studio."
                        ),
                        executive_summary=(
                            "Saya menjawab pertanyaan bisnis menggunakan semantic model dan metric "
                            "yang dipublish. Ajukan pertanyaan spesifik setelah memilih @Semantic model."
                            if greet_id
                            else "I answer business questions using the published semantic model and metrics. "
                            "Ask a specific question after choosing a @Semantic model."
                        ),
                        insights=[],
                        business_implications=[],
                        caveats=["Tidak ada query di turn ini." if greet_id else "No query ran on this turn."],
                        data_reference="Published semantic model capability catalog.",
                        chart_spec=None,
                    )
            if intent.attach_domain_catalog:
                precomputed = guidance.get("domain_capability_lines")
                if isinstance(precomputed, list) and precomputed:
                    insight_lines = precomputed
                else:
                    excluded = guidance.get("excluded_focus")
                    excluded_key = excluded if isinstance(excluded, str) else None
                    insight_lines = deps.semantic_context.domain_capability_insight_lines(
                        exclude_focus=excluded_key,
                        language=detect_language(original_question),
                    )
                answer = answer.model_copy(update={"insights": insight_lines})
            return {
                **state,
                "conversational_intent": intent_payload,
                "request_id": state.get("request_id") or str(uuid.uuid4()),
                "status": "SUCCESS",
                "strategy": "conversational",
                "answer": answer.model_dump(),
                "chart_spec": None,
                "query_result": {"columns": [], "rows": [], "row_count": 0, "execution_ms": 0},
                "timings": _with_timing(state, "context_ms", _elapsed(started)),
            }
        # ChatService pre-resolves with session analysis context (follow-ups).
        # Re-resolving here without that context breaks branch→material drills.
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
            "conversational_intent": intent_payload,
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
        if resolution.get("status") == "history_only":
            prior = resolution.get("prior_query_result") or {}
            focus = resolution.get("focus_entity") if isinstance(resolution.get("focus_entity"), dict) else {}
            prior_turn = resolution.get("prior_turn") if isinstance(resolution.get("prior_turn"), dict) else {}
            data_ref = str(prior_turn.get("data_reference") or "prior_governed_turn")
            update.update(
                skip_query_pipeline=True,
                strategy="history_only_analysis",
                query_result=prior,
                query_plan={"strategy": "history_only", "metrics": [resolution.get("metric")]},
                validated_sql=data_ref,
                governed_partial_caveats=[
                    "Turn ini menganalisis ulang angka governed dari pertanyaan sebelumnya; "
                    "tidak ada query baru dijalankan."
                    if detect_language(str(state.get("question") or "")) == "id"
                    else "This turn re-analyzes the governed numbers from the previous question; no new query was run."
                ],
                inquiry_brief={
                    "mode": "history_only_analysis",
                    "prior_turn_question": prior_turn.get("question"),
                    "focus_entity_id": focus.get("id"),
                    "focus_rank": focus.get("rank"),
                    "last_metric": resolution.get("metric"),
                },
            )
        return update

    async def resolve_datasource(state: AskDataState) -> AskDataState:
        started = perf_counter()
        if state.get("status") or state.get("skip_query_pipeline"):
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
        entity_lookup = False
        drill_state: dict[str, Any] | None = None
        runtime_join_patch: dict[str, Any] = {}
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
        if resolution.get("status") == "resolved":
            partial_caveats = _governed_partial_caveats(resolution, detect_language(state["question"])) + _partner_scope_caveats(
                state["question"], resolution
            )
            metric = str(resolution["metric"])
            definition = resolution.get("definition") or deps.semantic_context.metric_definition(metric)
            dataset_name = str(definition.get("base_dataset") or "")
            fields = set(deps.semantic_context.registry.dataset_fields.get(dataset_name, ()))
            entity_lookup = is_governed_entity_lookup(state["question"], fields)
            allowed_dims = set(definition.get("allowed_dimensions") or [])
            pre_brief = build_inquiry_brief(
                state["question"],
                semantic_resolution=resolution,
                session_last_metric=state.get("session_last_metric"),
            )
            rank_dims = rank_dimensions_for_brief(pre_brief, allowed_dims)
            if state.get("judge_retry_plan") and rank_dims is None and pre_brief.get("wants_rank"):
                rank_dims = rank_dimensions_for_brief(
                    {**pre_brief, "wants_dc_grain": True},
                    allowed_dims,
                )
            dimensions = resolution.get("dimensions")
            if rank_dims is not None and resolution.get("matched_alias") != "follow_up_context":
                dimensions = rank_dims
            extra_predicates = resolution.get("follow_up_entity_filters")
            if not isinstance(extra_predicates, list):
                extra_predicates = None
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
                )
                value_filters = value_resolution.filters
                indonesian = detect_language(state["question"]) == "id"
                if value_filters:
                    extra_predicates = [*(extra_predicates or []), *(f.predicate() for f in value_filters)]
                    scope = "; ".join(f.describe() for f in value_filters)
                    partial_caveats = [*partial_caveats, f"Difilter ke: {scope}." if indonesian else f"Filtered to: {scope}."]
                for heard, value in value_resolution.corrections:
                    partial_caveats = [
                        *partial_caveats,
                        f"“{heard}” dibaca sebagai {value}." if indonesian else f"“{heard}” was read as {value}.",
                    ]
                for heard, candidates in value_resolution.suggestions:
                    options = " / ".join(candidates)
                    partial_caveats = [
                        *partial_caveats,
                        f"“{heard}” tidak dipakai sebagai filter karena belum pasti. Maksudnya {options}? Tulis nama lengkapnya agar hasilnya terfilter."
                        if indonesian
                        else f"“{heard}” was not used as a filter because it is not certain. Did you mean {options}? Spell it out to filter the result.",
                    ]
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
                and resolution.get("matched_alias") != "follow_up_context"
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
            from app.semantic.runtime_extensions import governed_join_state_patch

            join_patch = governed_join_state_patch(
                extensions=deps.semantic_context.registry.runtime_extensions,
                datasets=deps.semantic_context.registry.datasets,
                sql=governed_sql,
                datasource_context=state.get("datasource_context")
                if isinstance(state.get("datasource_context"), dict)
                else None,
            )
            if join_patch:
                runtime_join_patch = join_patch
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
            **runtime_join_patch,
            "strategy": plan.strategy,
            "query_plan": plan.model_dump(),
            "sql": plan.sql or "",
            "governed_partial_caveats": partial_caveats,
            "governed_entity_lookup": entity_lookup,
            "drill_across": drill_state or {},
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
            if _should_try_local_agent_second(state, deps):
                fallback_answer = await _try_local_agent_fallback(state, deps)
                if fallback_answer is not None:
                    update.update(
                        status="SUCCESS",
                        strategy="local_agent_exploratory",
                        answer=fallback_answer,
                        chart_spec=None,
                        query_result={"columns": [], "rows": [], "row_count": 0, "execution_ms": 0},
                    )
        elif plan.strategy == "unsupported":
            fallback_answer = (
                await _try_local_agent_fallback(state, deps)
                if _should_try_local_agent_second(state, deps)
                else None
            )
            if fallback_answer is not None:
                update.update(
                    status="SUCCESS",
                    strategy="local_agent_exploratory",
                    answer=fallback_answer,
                    chart_spec=None,
                    query_result={"columns": [], "rows": [], "row_count": 0, "execution_ms": 0},
                )
            else:
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
        resolution = state.get("semantic_resolution") if isinstance(state.get("semantic_resolution"), dict) else {}
        catalog_entity = resolution.get("follow_up_catalog_entity")
        if not rows and not isinstance(catalog_entity, dict):
            session_ctx = state.get("session_analysis_context")
            if isinstance(session_ctx, dict) and session_ctx.get("result_catalog"):
                from app.services.follow_up import plan_follow_up

                plan = plan_follow_up(str(state.get("question") or ""), session_ctx)
                if plan and plan.filter_entity:
                    catalog_entity = plan.filter_entity
        if not rows and isinstance(catalog_entity, dict):
            synthetic = _row_from_follow_up_catalog(catalog_entity)
            if synthetic:
                dim = next(k for k in synthetic if k != "metric_value")
                columns = [dim, "metric_value"] if "metric_value" in synthetic else [dim]
                rows = [synthetic]
                result = {
                    **result,
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows),
                }
                update["query_result"] = result
        if not rows:
            metric_name = str(resolution.get("metric") or "")
            if "stock_warehouse_to_sell_in" in metric_name:
                update.update(
                    status="CLARIFICATION",
                    strategy="clarification",
                    answer=_safe_answer(
                        "Data perbandingan stok Reference vs sell-in untuk material tersebut tidak lengkap "
                        "pada periode Q4 2024. Anda bisa minta rincian sell-in per bulan untuk material yang sama."
                        if detect_language(str(state.get("question") or "")) == "id"
                        else "The stock versus sell-in comparison for this material is incomplete in Q4 2024. "
                        "You can ask for the monthly sell-in of the same material."
                    ),
                    chart_spec=None,
                )
                return update
            if resolution.get("matched_alias") == "follow_up_context":
                fe = re.search(r"\b(FE\d+)\b", str(state.get("question") or ""), flags=re.IGNORECASE)
                if fe:
                    code = fe.group(1).upper()
                    rows = [{"material": code, "metric_value": 0}]
                    result = {
                        **result,
                        "columns": ["material", "metric_value"],
                        "rows": rows,
                        "row_count": len(rows),
                    }
                    update["query_result"] = result
            if resolution.get("follow_up_plan", {}).get("to_grain") == "material" and isinstance(
                catalog_entity, dict
            ):
                syn = _row_from_follow_up_catalog(catalog_entity)
                if syn:
                    dim = next(k for k in syn if k != "metric_value")
                    rows = [syn]
                    result = {
                        **result,
                        "columns": [dim, "metric_value"] if "metric_value" in syn else [dim],
                        "rows": rows,
                        "row_count": len(rows),
                    }
                    update["query_result"] = result
        if not rows:
            update.update(
                status="NO_DATA",
                answer=_safe_answer(
                    "Tidak ada data yang cocok untuk pertanyaan dan filter tersebut."
                    if detect_language(state.get("original_question") or state["question"]) == "id"
                    else "No data matches this question and these filters."
                ),
                chart_spec=None,
            )
            return update
        if state.get("governed_entity_lookup") and resolution.get("matched_alias") != "follow_up_context":
            metric_values = [
                row.get("metric_value")
                for row in rows
                if isinstance(row, dict) and "metric_value" in row
            ]
            if not metric_values or all(value is None for value in metric_values):
                update.update(
                    status="NO_DATA",
                    answer=_safe_answer(
                        "Tidak ada nilai metrik yang bisa dihitung untuk kombinasi material/cabang "
                        "dan periode yang diminta (misalnya sell-in nol atau stok tidak tercatat "
                        "pada periode Q4 2024)."
                        if detect_language(str(state.get("question") or "")) == "id"
                        else "No metric value can be calculated for the requested material or branch and period "
                        "(for example sell-in is zero or stock was not recorded in Q4 2024).",
                        caveats=list(state.get("governed_partial_caveats") or []),
                    ),
                    chart_spec=None,
                )
                return update
        if rows and isinstance(resolution, dict) and resolution.get("status") == "resolved":
            from app.services.analysis_enrichment import apply_analysis_enrichment

            enriched = await apply_analysis_enrichment(
                question=str(state.get("question") or ""),
                resolution=resolution,
                result=update.get("query_result") or result,
                semantic_context=deps.semantic_context,
                query_executor=deps.query_executor.execute,
                request_id=str(state.get("request_id") or ""),
            )
            if enriched:
                meta = enriched.pop("analysis_enrichment", None) or {}
                enriched.pop("analysis_mode", None)
                partial = list(update.get("governed_partial_caveats") or state.get("governed_partial_caveats") or [])
                caveat = meta.get("caveat")
                if isinstance(caveat, str) and caveat and caveat not in partial:
                    partial.append(caveat)
                brief = dict(update.get("inquiry_brief") or state.get("inquiry_brief") or {})
                brief["analysis_mode"] = meta.get("mode") or brief.get("analysis_mode")
                if meta.get("company_total_metric_value") is not None:
                    brief["company_total_metric_value"] = meta.get("company_total_metric_value")
                update["query_result"] = enriched
                update["governed_partial_caveats"] = partial
                update["inquiry_brief"] = brief
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
        }
        if (state.get("drill_across") or {}).get("columns"):
            user_payload["result_columns_are_metrics"] = state["drill_across"]["columns"]
        if (state.get("drill_across") or {}).get("kind"):
            drill_info = state["drill_across"]
            user_payload["comparison"] = {"kind": drill_info["kind"], **(drill_info.get("meta") or {})}
        if state.get("judge_synthesis_hint"):
            user_payload["reviewer_hint"] = state["judge_synthesis_hint"]
        if state.get("ask_data_space_instructions"):
            user_payload["space_instructions"] = state["ask_data_space_instructions"]
        if state.get("strategy") == "history_only_analysis":
            user_payload["history_only_analysis"] = True
            user_payload["prior_turn"] = (resolution or {}).get("prior_turn")
            user_payload["session_analysis_context"] = state.get("session_analysis_context")
            user_payload["conversation_history"] = state.get("conversation_history")
        analyst_prompt = _prompt("result_analyst.md")
        if state.get("strategy") == "history_only_analysis":
            analyst_prompt = analyst_prompt + "\n" + _prompt("result_analyst_history_only.md")
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
                    max_tokens=1800,
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
        return {
            **state,
            "status": "SUCCESS",
            "answer": analysis.model_dump(),
            "chart_spec": chart.model_dump() if chart else None,
            "timings": _with_timing(state, "analysis_ms", _elapsed(started)),
            "judge_retry_synthesize": False,
            "judge_synthesis_hint": "",
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
        if state.get("skip_query_pipeline"):
            return "analyze_result"
        return "end" if state.get("status") else "resolve_datasource"

    def after_resolve_datasource(state: AskDataState) -> str:
        return "end" if state.get("status") else "plan_query"

    def after_plan(state: AskDataState) -> str:
        return "end" if state.get("status") else "validate_query"

    def after_validate(state: AskDataState) -> str:
        return "end" if state.get("status") else "execute_query"

    def after_execute(state: AskDataState) -> str:
        return "end" if state.get("status") else "analyze_result"

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
        {"resolve_datasource": "resolve_datasource", "analyze_result": "analyze_result", "end": END},
    )
    graph.add_conditional_edges(
        "resolve_datasource",
        after_resolve_datasource,
        {"plan_query": "plan_query", "end": END},
    )
    graph.add_conditional_edges("plan_query", after_plan, {"validate_query": "validate_query", "end": END})
    graph.add_conditional_edges("validate_query", after_validate, {"execute_query": "execute_query", "end": END})
    graph.add_conditional_edges("execute_query", after_execute, {"analyze_result": "analyze_result", "end": END})
    graph.add_edge("analyze_result", "judge_answer")
    graph.add_conditional_edges(
        "judge_answer",
        after_judge,
        {"plan_query": "plan_query", "analyze_result": "analyze_result", "end": END},
    )
    return graph.compile()
