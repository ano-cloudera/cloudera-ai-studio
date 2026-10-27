from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Any
import uuid

from app.core.config import Settings
from app.core.models import (
    AnalysisOutput,
    AskDataClarification,
    AskDataRequest,
    AskDataResponse,
    ChartSpec,
    ClarificationOption,
    LlmUsage,
    QueryData,
    SemanticRuntimeMeta,
    Timings,
)
from app.llm.usage_context import (
    UsageTracker,
    attach_usage_tracker,
    finish_request_usage,
    start_request_usage,
)
from app.stores.factory import build_conversation_store, build_usage_store
from app.stores.protocols import ConversationStoreProtocol, UsageStoreProtocol
from app.db.platform_engine import get_session_factory
from app.projects.resolver import load_default_project, resolve_ossie_project_dir
from app.semantic_runtime.loader import RuntimeContextBundle, SemanticRuntimeLoader
from app.prompt_management.runtime import prompt_runtime
from app.db.base import DataBackendError
from app.ask_data.datasource_executor import RoutedQueryExecutor
from app.ask_data.legacy_executor import DuckDBQueryExecutor, ImpalaQueryExecutor, build_query_executor
from app.ask_data.validation import validate_ask_data_sql
from app.graph.workflow import WorkflowDependencies, build_workflow
from app.ai_registry.hybrid_provider_registry import HybridProviderRegistry
from app.ai_registry.errors import AiRegistryError
from app.ai_registry.runtime_errors import RegistryRuntimeError
from app.core.models import ModelResolutionMeta
from app.llm.registry import ProviderRegistry
from app.semantic.context import SemanticContextService
from app.services.ask_data_routing import resolve_ask_data_route, v3_agent_available
from app.services.conversational import TurnUnderstanding, understand_turn
from app.services.follow_up import analysis_context_from_history, try_history_only_analysis_resolution
from app.services.question_contextualize import resolve_question_for_pipeline
from app.services.session_context import build_session_frame, capability_session_hint
from app.services.local_agent_client import LocalAgentClient, LocalAgentError
from app.services.ossie_trace import NODE_LABELS, trace_detail
from app.services.v3_answer_polish import polish_v3_answer
from app.chat.context_sources import ContextSourceError, apply_context_sources, structured_data_sources
from app.ask_data.structured_context_resolver import StructuredAskPrecedence, resolve_structured_ask
from app.services.rag_chat import run_rag_turn, stream_rag_turn
from app.services.user_facing_error import explain_failure


logger = logging.getLogger(__name__)

_NO_GOVERNED_REF = "no governed query result attached"


def _normalize_governed_v3_response(response: AskDataResponse) -> AskDataResponse:
    ref = (response.answer.data_reference or "").casefold()
    missing = _NO_GOVERNED_REF in ref and response.data.row_count == 0
    if response.strategy != "governed" or response.status != "SUCCESS" or not missing:
        return response
    caveats = list(response.answer.caveats)
    caveat = (
        "Jawaban belum terhubung ke hasil query governed Impala (tidak ada query_id atau baris data). "
        "Ulangi dengan pertanyaan analitik yang spesifik."
    )
    if caveat not in caveats:
        caveats.insert(0, caveat)
    answer = response.answer.model_copy(update={"caveats": caveats})
    return response.model_copy(update={"status": "NO_DATA", "answer": answer})


def _session_last_metric(history: list[dict]) -> str | None:
    for entry in reversed(history):
        frame = entry.get("session_frame")
        if not isinstance(frame, dict):
            continue
        metric = frame.get("last_metric")
        if isinstance(metric, str) and metric.strip():
            return metric.strip()
    return None


class ChatService:
    def __init__(
        self,
        settings: Settings,
        *,
        dependencies: WorkflowDependencies | None = None,
        history: ConversationStoreProtocol | None = None,
        usage_store: UsageStoreProtocol | None = None,
    ) -> None:
        self.settings = settings
        self.usage_tracker = UsageTracker()
        attach_usage_tracker(self.usage_tracker)
        context = SemanticContextService(resolve_ossie_project_dir(settings))
        session_factory = get_session_factory(settings.database_url) if (settings.database_url or "").strip() else None
        query_executor = (
            RoutedQueryExecutor(settings, session_factory)
            if session_factory is not None
            else build_query_executor(settings)
        )
        legacy_registry = ProviderRegistry(settings)
        hybrid_registry = HybridProviderRegistry(
            settings,
            legacy=legacy_registry,
            session_factory=session_factory,
        )
        self.dependencies = dependencies or WorkflowDependencies(
            semantic_context=context,
            provider_registry=hybrid_registry,
            query_executor=query_executor,
            sql_validator=self._validate_ask_data_sql,
            validation_context=context,
            settings=settings,
            session_factory=session_factory,
            local_agent_client=LocalAgentClient(settings),
            judge_max_iterations=settings.judge_max_iterations,
            judge_enabled=settings.judge_enabled,
            usage_tracker=self.usage_tracker,
        )
        self.workflow = build_workflow(self.dependencies)
        self.history = history or build_conversation_store(settings)
        self.usage_store = usage_store or build_usage_store(settings)
        self._runtime_meta: SemanticRuntimeMeta | None = None
        self._runtime_bundle: RuntimeContextBundle | None = None
        self._project_scope: tuple[str, str] | None = None
        self._active_resolution: ModelResolutionMeta | None = None
        self.apply_runtime_bundle(SemanticRuntimeLoader.get(settings).get_bundle())

    def _validate_ask_data_sql(self, sql: str, state: dict[str, Any]) -> Any:
        return validate_ask_data_sql(
            sql,
            self.dependencies.semantic_context,
            state=state if isinstance(state, dict) else None,
            max_rows=self.settings.sql_max_rows,
        )

    def apply_runtime_bundle(self, bundle: RuntimeContextBundle) -> None:
        ctx = bundle.context
        if self.dependencies.semantic_context is not ctx:
            self.dependencies = WorkflowDependencies(
                semantic_context=ctx,
                provider_registry=self.dependencies.provider_registry,
                query_executor=self.dependencies.query_executor,
                sql_validator=self.dependencies.sql_validator,
                validation_context=ctx,
                settings=self.dependencies.settings,
                session_factory=self.dependencies.session_factory,
                local_agent_client=self.dependencies.local_agent_client,
                judge_max_iterations=self.dependencies.judge_max_iterations,
                judge_enabled=self.dependencies.judge_enabled,
                usage_tracker=self.dependencies.usage_tracker,
            )
            self.workflow = build_workflow(self.dependencies)
        self._runtime_bundle = bundle
        self._runtime_meta = SemanticRuntimeMeta(
            mode=bundle.mode,
            deployment_id=str(bundle.deployment_id) if bundle.deployment_id else None,
            semantic_version_id=str(bundle.semantic_version_id) if bundle.semantic_version_id else None,
            registry_version_number=bundle.registry_version_number,
            artifact_checksum=bundle.artifact_checksum,
            health=bundle.health,
        )

    def bootstrap_runtime_from_db(self) -> None:
        if self.settings.state_store.strip().lower() != "postgres" or not (self.settings.database_url or "").strip():
            self.apply_runtime_bundle(SemanticRuntimeLoader.get(self.settings).get_bundle())
            return
        project = load_default_project(self.settings)
        if project is None:
            self.apply_runtime_bundle(SemanticRuntimeLoader.get(self.settings).get_bundle())
            return
        self._project_scope = (str(project.workspace_id), str(project.id))
        factory = get_session_factory(self.settings.database_url)
        with factory() as session:
            bundle = SemanticRuntimeLoader.get(self.settings).refresh(
                session,
                workspace_id=project.workspace_id,
                project_id=project.id,
            )
        self.apply_runtime_bundle(bundle)

    def _sync_runtime_for_request(self) -> None:
        self.apply_runtime_bundle(SemanticRuntimeLoader.get(self.settings).get_bundle())

    def _resolve_provider(self, request: AskDataRequest, request_id: str):
        provider = self.dependencies.provider_registry.resolve(request.provider, request.model)
        return self.usage_tracker.wrap(provider, request_id)

    def _resolution_meta_from_registry(self) -> ModelResolutionMeta | None:
        reg = self.dependencies.provider_registry
        if not isinstance(reg, HybridProviderRegistry):
            return None
        resolution = reg.last_resolution
        if resolution is None or not resolution.uses_registry:
            return None
        return ModelResolutionMeta(
            capability=resolution.capability,
            assignment_source=resolution.source,
            provider_type=resolution.provider_type,
            model_key=resolution.model_key,
            registry_model_id=resolution.runtime_model_id,
        )

    def _with_resolution_meta(self, response: AskDataResponse) -> AskDataResponse:
        meta = self._active_resolution or self._resolution_meta_from_registry()
        if meta is None:
            return response
        return response.model_copy(update={"model_resolution": meta})

    def _registry_error_response(
        self,
        request: AskDataRequest,
        *,
        request_id: str,
        exc: RegistryRuntimeError | AiRegistryError,
        started: float | None = None,
    ) -> AskDataResponse:
        from time import perf_counter

        elapsed = round((perf_counter() - started) * 1000, 3) if started else 0.0
        text = exc.message
        return AskDataResponse(
            request_id=request_id,
            session_id=request.session_id,
            status="ERROR",
            provider=request.provider,
            model=request.model,
            strategy="unsupported",
            answer=AnalysisOutput(
                direct_answer=text,
                executive_summary=text,
                insights=[],
                business_implications=[],
                caveats=[exc.code],
                data_reference="model registry configuration error",
                chart_spec=None,
            ),
            data=QueryData(),
            chart_spec=None,
            timings=Timings(total_ms=elapsed),
        )

    def normalize_request(self, request: AskDataRequest) -> AskDataRequest:
        if not request.context_sources:
            return request
        if self.settings.state_store.strip().lower() != "postgres" or not (self.settings.database_url or "").strip():
            raise ContextSourceError(
                "context_unavailable",
                "Knowledge library context requires platform metadata storage",
                503,
            )
        project = load_default_project(self.settings)
        if project is None:
            raise ContextSourceError("project_not_found", "Default project is not configured", 503)
        history = self.history.load(request.session_id, limit=8)
        factory = get_session_factory(self.settings.database_url)
        with factory() as session:
            return apply_context_sources(
                request,
                session=session,
                project_id=project.id,
                conversation_history=history,
                settings=self.settings,
            )

    def _prepare_registry_request(
        self,
        request: AskDataRequest,
        *,
        capability: str,
    ) -> AskDataRequest:
        reg = self.dependencies.provider_registry
        if not isinstance(reg, HybridProviderRegistry):
            return request
        ws_id, proj_id = (self._project_scope or (None, None))
        if not ws_id or not proj_id:
            project = load_default_project(self.settings)
            if project is None:
                return request
            ws_id, proj_id = str(project.workspace_id), str(project.id)
        resolution = reg.prepare_request(
            capability=capability,
            workspace_id=ws_id,
            project_id=proj_id,
            fallback_provider=request.provider,
            fallback_model=request.model,
        )
        if not resolution.uses_registry and capability == "ASK_DATA":
            resolution = reg.prepare_request(
                capability="CHAT_DEFAULT",
                workspace_id=ws_id,
                project_id=proj_id,
                fallback_provider=request.provider,
                fallback_model=request.model,
            )
        self._active_resolution = self._resolution_meta_from_registry()
        if not resolution.uses_registry:
            return request
        legacy_provider = resolution.legacy_provider or request.provider
        if legacy_provider not in {"qwen", "gemini", "openai"}:
            legacy_provider = request.provider
        return request.model_copy(
            update={
                "provider": legacy_provider,  # type: ignore[arg-type]
                "model": resolution.legacy_model or request.model,
            }
        )

    def _attach_usage(self, request: AskDataRequest, response: AskDataResponse) -> AskDataResponse:
        acc = finish_request_usage(response.request_id)
        if acc is None:
            return response
        usage = LlmUsage(
            prompt_tokens=acc.prompt_tokens,
            completion_tokens=acc.completion_tokens,
            total_tokens=acc.total_tokens,
            llm_calls=acc.llm_calls,
        )
        self.usage_store.record(
            request_id=response.request_id,
            session_id=request.session_id,
            provider=request.provider,
            model=request.model,
            strategy=str(response.strategy),
            status=str(response.status),
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            llm_calls=usage.llm_calls,
        )
        return response.model_copy(update={"usage": usage})

    def delete_session_history(self, session_id: str) -> int:
        return self.history.delete_session(session_id)

    @asynccontextmanager
    async def _prompt_resolution_scope(self):
        project = load_default_project(self.settings)
        if project is None:
            yield
            return
        with prompt_runtime(self.settings, project.workspace_id, project.id):
            yield

    def _v3_client(self) -> LocalAgentClient | None:
        client = self.dependencies.local_agent_client
        if client is None or not client.enabled:
            return None
        return client

    def _structured_precedence(
        self,
        request: AskDataRequest,
        *,
        question: str,
    ) -> StructuredAskPrecedence | None:
        if self.dependencies.session_factory is None or not (self.settings.database_url or "").strip():
            if structured_data_sources(request.context_sources):
                return StructuredAskPrecedence(
                    force_ossie=True,
                    skip_auto_semantic_when_explicit=True,
                    resolution=None,
                    clarification=None,
                    explicit_error="Structured data context requires platform metadata storage.",
                    runtime_bundle=None,
                    context_mode=None,
                )
            return None
        project = load_default_project(self.settings)
        if project is None:
            return None
        self._project_scope = (str(project.workspace_id), str(project.id))
        with self.dependencies.session_factory() as session:
            return resolve_structured_ask(
                session,
                settings=self.settings,
                workspace_id=project.workspace_id,
                project_id=project.id,
                request=request,
                semantic_context=self.dependencies.semantic_context,
                question=question,
            )

    def _clarification_response(
        self,
        request: AskDataRequest,
        *,
        request_id: str,
        payload,
        started: float,
    ) -> AskDataResponse:
        from time import perf_counter

        elapsed = round((perf_counter() - started) * 1000, 3) if started else 0.0
        options = [
            ClarificationOption(type=item["type"], id=item["id"], name=item["name"])
            for item in payload.options
        ]
        message = payload.message
        return AskDataResponse(
            request_id=request_id,
            session_id=request.session_id,
            status="clarification_required",
            provider=request.provider,
            model=request.model,
            strategy="clarification",
            answer=AnalysisOutput(
                direct_answer=message,
                executive_summary=message,
                insights=[],
                business_implications=[],
                caveats=[payload.reason],
                data_reference="clarification_required",
                chart_spec=None,
            ),
            data=QueryData(),
            chart_spec=None,
            timings=Timings(total_ms=elapsed),
            clarification=AskDataClarification(reason=payload.reason, message=message, options=options),
        )

    def _explicit_context_error_response(
        self,
        request: AskDataRequest,
        *,
        request_id: str,
        message: str,
        started: float,
    ) -> AskDataResponse:
        from time import perf_counter

        elapsed = round((perf_counter() - started) * 1000, 3) if started else 0.0
        return AskDataResponse(
            request_id=request_id,
            session_id=request.session_id,
            status="ERROR",
            provider=request.provider,
            model=request.model,
            strategy="unsupported",
            answer=AnalysisOutput(
                direct_answer=message,
                executive_summary=message,
                insights=[],
                business_implications=[],
                caveats=["explicit_context_unavailable"],
                data_reference="explicit structured context",
                chart_spec=None,
            ),
            data=QueryData(),
            chart_spec=None,
            timings=Timings(total_ms=elapsed),
        )

    def _route_for_question(
        self,
        question: str,
        *,
        session_last_metric: str | None = None,
        session_analysis_context: dict[str, Any] | None = None,
        turn_understanding: TurnUnderstanding | None = None,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        if session_analysis_context and conversation_history:
            history_only = try_history_only_analysis_resolution(
                question,
                session_analysis_context,
                conversation_history,
                understanding=turn_understanding,
            )
            if history_only:
                route = resolve_ask_data_route(
                    question, self.settings, semantic_resolution=history_only
                )
                return route, history_only
        resolution = self.dependencies.semantic_context.resolve(
            question,
            session_last_metric=session_last_metric,
            session_analysis_context=session_analysis_context,
            turn_understanding=turn_understanding.model_dump() if turn_understanding else None,
        )
        route = resolve_ask_data_route(question, self.settings, semantic_resolution=resolution)
        return route, resolution

    def _session_frame_for_turn(
        self,
        request: AskDataRequest,
        response: AskDataResponse,
        workflow_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolution = (workflow_state or {}).get("semantic_resolution") or {}
        metric = resolution.get("metric")
        dimensions = resolution.get("dimensions")
        return build_session_frame(
            question=request.question,
            status=response.status,
            strategy=response.strategy,
            rows=response.data.rows,
            metric=str(metric) if isinstance(metric, str) else None,
            dimensions=[str(item) for item in dimensions] if isinstance(dimensions, list) else None,
        )

    def _persist_turn(
        self,
        request: AskDataRequest,
        response: AskDataResponse,
        chart: ChartSpec | None,
        *,
        workflow_state: dict[str, Any] | None = None,
        session_frame_override: dict[str, Any] | None = None,
    ) -> None:
        self.history.append(
            request.session_id,
            request.question,
            response.answer,
            response.data.rows,
            chart,
            request.provider,
            request.model,
            status=response.status,
            strategy=response.strategy,
            session_frame=session_frame_override
            or self._session_frame_for_turn(request, response, workflow_state),
        )

    async def _run_rag(self, request: AskDataRequest, *, request_id: str) -> AskDataResponse:
        conversation_history = self.history.load(request.session_id, limit=8)
        provider = self._resolve_provider(request, request_id)
        response, session_frame = await run_rag_turn(
            self.settings,
            request,
            request_id=request_id,
            conversation_history=conversation_history,
            llm_provider=provider,
        )
        response = self._attach_usage(request, response)
        self._persist_turn(request, response, None, session_frame_override=session_frame or None)
        return response

    async def _stream_rag(self, request: AskDataRequest, *, request_id: str):
        conversation_history = self.history.load(request.session_id, limit=8)
        provider = self._resolve_provider(request, request_id)
        async for event in stream_rag_turn(
            self.settings,
            request,
            request_id=request_id,
            conversation_history=conversation_history,
            llm_provider=provider,
        ):
            if event.get("type") == "done":
                response = self._attach_usage(request, event["response"])
                frame = event.get("session_frame")
                self._persist_turn(
                    request,
                    response,
                    None,
                    session_frame_override=frame if isinstance(frame, dict) else None,
                )
                yield {"type": "done", "response": response}
                return
            yield event

    async def _run_via_tempo_agent_v3(
        self,
        request: AskDataRequest,
        *,
        request_id: str,
        question: str,
        client: LocalAgentClient,
    ) -> AskDataResponse:
        started = perf_counter()
        try:
            response = await client.ask_data(
                question,
                session_id=request.session_id,
                provider=request.provider,
                model=request.model,
                request_id=request_id,
                answer_language="id",
            )
        except LocalAgentError as exc:
            logger.warning("tempo_agent_v3_primary_failed request_id=%s code=%s", request_id, exc.code)
            provider = self.dependencies.provider_registry.resolve(request.provider, request.model)
            answer = await explain_failure(
                provider=provider,
                question=question,
                failure={"kind": "internal", "code": f"LOCAL_AGENT_{exc.code}"},
                request_id=request_id,
            )
            elapsed = round((perf_counter() - started) * 1000, 3)
            return AskDataResponse(
                request_id=request_id,
                session_id=request.session_id,
                status="ERROR",
                provider=request.provider,
                model=request.model,
                strategy="unsupported",
                answer=answer,
                data=QueryData(),
                chart_spec=None,
                timings=Timings(total_ms=elapsed),
            )
        timings = response.timings.model_copy(update={"total_ms": round((perf_counter() - started) * 1000, 3)})
        response = polish_v3_answer(
            _normalize_governed_v3_response(response.model_copy(update={"timings": timings}))
        )
        self._persist_turn(request, response, response.chart_spec)
        logger.info(
            "ask_data_v3 request_id=%s session_id=%s strategy=%s status=%s total_ms=%s",
            request_id,
            request.session_id,
            response.strategy,
            response.status,
            timings.total_ms,
        )
        return response

    def _routing_mode(self) -> str:
        return (self.settings.ask_data_routing or "auto").strip().lower()

    def _v3_fallback_to_ossie_on_error(self) -> bool:
        return self._routing_mode() == "auto" and not self.settings.local_agent_primary

    async def _understand_turn(
        self,
        request: AskDataRequest,
        conversation_history: list[dict],
        *,
        request_id: str,
    ) -> TurnUnderstanding:
        provider = self._resolve_provider(request, request_id)
        return await understand_turn(
            provider=provider,
            question=request.question,
            conversation_history=conversation_history,
        )

    def _build_initial_state(
        self,
        request: AskDataRequest,
        *,
        request_id: str,
        question: str,
        resolution: dict[str, Any],
        conversation_history: list[dict],
        session_analysis_context: dict[str, Any] | None = None,
        turn_understanding: TurnUnderstanding | None = None,
    ) -> dict[str, Any]:
        state: dict[str, Any] = {
            **request.model_dump(),
            "original_question": request.question,
            "question": question,
            "semantic_resolution": resolution,
            "conversation_history": [
                {"question": item["question"], "answer": item["answer"]}
                for item in conversation_history
            ],
            "session_last_metric": _session_last_metric(conversation_history),
            "request_id": request_id,
            "retry_count": 0,
            "timings": {},
        }
        if turn_understanding is not None:
            payload = turn_understanding.model_dump()
            state["turn_understanding"] = payload
            state["conversational_intent"] = payload
        if session_analysis_context:
            state["session_analysis_context"] = session_analysis_context
        if conversation_history:
            state["session_capability_hint"] = capability_session_hint(conversation_history)
        bundle = self._runtime_bundle
        if bundle is not None:
            state["runtime_mode"] = bundle.mode
            if bundle.semantic_version_id:
                state["semantic_version_id"] = str(bundle.semantic_version_id)
        if self._project_scope:
            state["workspace_id"], state["project_id"] = self._project_scope
        if resolution.get("datasource_context"):
            state["datasource_context"] = resolution["datasource_context"]
        if resolution.get("raw_table_policy"):
            state["raw_table_policy"] = resolution["raw_table_policy"]
        if resolution.get("context_mode"):
            state["context_mode"] = resolution["context_mode"]
        elif resolution.get("status") == "raw_table":
            state["context_mode"] = "RAW_TABLE"
        elif resolution.get("explicit_structured") and resolution.get("status") in {
            "resolved",
            "needs_clarification",
            "fallback",
        }:
            state["context_mode"] = "GOVERNED_SEMANTIC"
        return state

    def _response_from_state(
        self,
        request: AskDataRequest,
        *,
        request_id: str,
        state: dict[str, Any],
        started: float,
    ) -> AskDataResponse:
        answer = AnalysisOutput.model_validate(state["answer"])
        chart = ChartSpec.model_validate(state["chart_spec"]) if state.get("chart_spec") else None
        raw_data = dict(state.get("query_result") or {"columns": [], "rows": [], "row_count": 0, "execution_ms": 0})
        resolution = state.get("semantic_resolution") if isinstance(state.get("semantic_resolution"), dict) else {}
        plan = state.get("query_plan") if isinstance(state.get("query_plan"), dict) else {}
        metrics = plan.get("metrics") if isinstance(plan.get("metrics"), list) else []
        governed_metric = resolution.get("metric") if resolution.get("status") == "resolved" else None
        if not governed_metric and metrics:
            governed_metric = metrics[0]
        unit_format = None
        if governed_metric:
            definition = resolution.get("definition")
            if isinstance(definition, dict) and definition.get("unit_format"):
                unit_format = definition.get("unit_format")
            else:
                try:
                    unit_format = self.dependencies.semantic_context.metric_definition(str(governed_metric)).get(
                        "unit_format"
                    )
                except Exception:
                    unit_format = None
        if governed_metric:
            raw_data["governed_metric"] = str(governed_metric)
        if unit_format:
            raw_data["unit_format"] = str(unit_format)
        query_result = state.get("query_result") if isinstance(state.get("query_result"), dict) else {}
        for key in ("connector_type", "connector_name"):
            if query_result.get(key):
                raw_data[key] = query_result[key]
        timings = {**state.get("timings", {}), "total_ms": round((perf_counter() - started) * 1000, 3)}
        sql = state.get("validated_sql") or state.get("sql")
        governed_sql = str(sql).strip() if isinstance(sql, str) and sql.strip() else None
        context_mode = state.get("context_mode")
        if not context_mode:
            resolution_mode = resolution.get("context_mode")
            if isinstance(resolution_mode, str):
                context_mode = resolution_mode
        if not context_mode and resolution.get("status") == "raw_table":
            context_mode = "RAW_TABLE"
        if not context_mode and resolution.get("explicit_structured"):
            context_mode = "GOVERNED_SEMANTIC"
        return AskDataResponse(
            request_id=request_id,
            session_id=request.session_id,
            status=state.get("status", "ERROR"),
            provider=request.provider,
            model=request.model,
            strategy=state.get("strategy", "unsupported"),
            answer=answer,
            data=QueryData.model_validate(raw_data),
            chart_spec=chart,
            timings=Timings.model_validate(timings),
            retry_count=state.get("retry_count", 0),
            governed_sql=governed_sql,
            semantic_runtime=self._runtime_meta,
            context_mode=context_mode if context_mode in {"RAW_TABLE", "GOVERNED_SEMANTIC"} else None,
        )

    async def _stream_ossie_workflow(
        self,
        request: AskDataRequest,
        *,
        request_id: str,
        question: str,
        resolution: dict[str, Any],
        conversation_history: list[dict],
        session_analysis_context: dict[str, Any] | None = None,
        turn_understanding: TurnUnderstanding | None = None,
    ):
        started = perf_counter()
        initial = self._build_initial_state(
            request,
            request_id=request_id,
            question=question,
            resolution=resolution,
            conversation_history=conversation_history,
            session_analysis_context=session_analysis_context,
            turn_understanding=turn_understanding,
        )
        last_state: dict[str, Any] | None = None
        try:
            async for chunk in self.workflow.astream(initial):
                for node_name, state in chunk.items():
                    last_state = state
                    stage, label = NODE_LABELS.get(node_name, (node_name, node_name.replace("_", " ").title()))
                    detail = trace_detail(node_name, state)
                    yield {
                        "type": "progress",
                        "stage": stage,
                        "label": label,
                        "detail": detail,
                    }
            if last_state is None:
                raise RuntimeError("workflow produced no state")
            response = self._response_from_state(
                request, request_id=request_id, state=last_state, started=started
            )
            response = self._attach_usage(request, response)
            self._persist_turn(request, response, response.chart_spec, workflow_state=last_state)
            yield {"type": "done", "response": response}
        except DataBackendError as exc:
            logger.warning(
                "ask_data_backend_failed request_id=%s safe_error_code=%s",
                request_id,
                exc.code,
            )
            provider = self.dependencies.provider_registry.resolve(request.provider, request.model)
            answer = await explain_failure(
                provider=provider,
                question=request.question,
                failure={"kind": "data_backend", "code": exc.code},
                request_id=request_id,
            )
            elapsed = round((perf_counter() - started) * 1000, 3)
            err = AskDataResponse(
                request_id=request_id,
                session_id=request.session_id,
                status="ERROR",
                provider=request.provider,
                model=request.model,
                strategy="unsupported",
                answer=answer,
                data=QueryData(),
                chart_spec=None,
                timings=Timings(total_ms=elapsed),
            )
            yield {"type": "done", "response": self._attach_usage(request, err)}
        except Exception:
            logger.exception("ask_data_failed request_id=%s", request_id)
            provider = self.dependencies.provider_registry.resolve(request.provider, request.model)
            answer = await explain_failure(
                provider=provider,
                question=request.question,
                failure={"kind": "internal", "code": "UNEXPECTED"},
                request_id=request_id,
            )
            elapsed = round((perf_counter() - started) * 1000, 3)
            err = AskDataResponse(
                request_id=request_id,
                session_id=request.session_id,
                status="ERROR",
                provider=request.provider,
                model=request.model,
                strategy="unsupported",
                answer=answer,
                data=QueryData(),
                chart_spec=None,
                timings=Timings(total_ms=elapsed),
            )
            yield {"type": "done", "response": self._attach_usage(request, err)}

    async def run(self, request: AskDataRequest, *, force_ossie: bool = False) -> AskDataResponse:
        request_id = str(uuid.uuid4())
        start_request_usage(request_id)
        self._sync_runtime_for_request()
        self._active_resolution = None
        reg = self.dependencies.provider_registry
        if isinstance(reg, HybridProviderRegistry):
            reg.clear_request_context()
        async with self._prompt_resolution_scope():
            started = perf_counter()
            try:
                cap = "RAG_GENERATION" if request.mode == "rag" else "ASK_DATA"
                request = self._prepare_registry_request(request, capability=cap)
            except (RegistryRuntimeError, AiRegistryError) as exc:
                logger.warning(
                    "model_resolution_failed request_id=%s capability=%s code=%s",
                    request_id,
                    cap,
                    exc.code,
                )
                return self._registry_error_response(request, request_id=request_id, exc=exc, started=started)
            try:
                if request.mode == "rag":
                    logger.info("ask_data_route=rag request_id=%s session_id=%s", request_id, request.session_id)
                    out = await self._run_rag(request, request_id=request_id)
                    return self._with_resolution_meta(out)
                conversation_history = self.history.load(request.session_id, limit=8)
                session_metric = _session_last_metric(conversation_history)
                session_ctx = analysis_context_from_history(conversation_history)
                turn = await self._understand_turn(request, conversation_history, request_id=request_id)
                question = resolve_question_for_pipeline(request.question, conversation_history, turn)
                precedence = self._structured_precedence(request, question=question)
                structured_resolution: dict[str, Any] | None = None
                if precedence is not None:
                    if precedence.runtime_bundle is not None:
                        self.apply_runtime_bundle(precedence.runtime_bundle)
                    if precedence.clarification is not None:
                        return self._with_resolution_meta(
                            self._clarification_response(
                                request,
                                request_id=request_id,
                                payload=precedence.clarification,
                                started=started,
                            )
                        )
                    if precedence.explicit_error:
                        return self._with_resolution_meta(
                            self._explicit_context_error_response(
                                request,
                                request_id=request_id,
                                message=precedence.explicit_error,
                                started=started,
                            )
                        )
                    if precedence.resolution is not None:
                        structured_resolution = precedence.resolution
                        force_ossie = True
                if structured_resolution is not None:
                    route, resolution = "ossie", structured_resolution
                else:
                    route, resolution = self._route_for_question(
                        question,
                        session_last_metric=session_metric,
                        session_analysis_context=session_ctx or None,
                        turn_understanding=turn,
                        conversation_history=conversation_history,
                    )
                if turn.is_conversational:
                    logger.info("ask_data_route=conversational request_id=%s session_id=%s", request_id, request.session_id)
                    force_ossie = True
                if resolution.get("status") == "history_only":
                    force_ossie = True
                if structured_data_sources(request.context_sources):
                    force_ossie = True
                if not force_ossie and route == "v3" and v3_agent_available(self.settings):
                    client = self._v3_client()
                    if client is not None:
                        logger.info("ask_data_route=v3 request_id=%s session_id=%s", request_id, request.session_id)
                        v3_response = await self._run_via_tempo_agent_v3(
                            request, request_id=request_id, question=question, client=client
                        )
                        if v3_response.status != "ERROR" or not self._v3_fallback_to_ossie_on_error():
                            return self._with_resolution_meta(v3_response)
                        logger.info("ask_data_v3_failed_fallback_ossie request_id=%s", request_id)
                logger.info("ask_data_route=ossie request_id=%s session_id=%s", request_id, request.session_id)
                initial = self._build_initial_state(
                    request,
                    request_id=request_id,
                    question=question,
                    resolution=resolution,
                    conversation_history=conversation_history,
                    session_analysis_context=session_ctx or None,
                    turn_understanding=turn,
                )
                try:
                    state = await self.workflow.ainvoke(initial)
                    response = self._response_from_state(
                        request, request_id=request_id, state=state, started=started
                    )
                    response = self._attach_usage(request, response)
                    self._persist_turn(request, response, response.chart_spec, workflow_state=state)
                    logger.info(
                        "ask_data request_id=%s session_id=%s provider=%s model=%s strategy=%s status=%s retry_count=%s timings=%s turn_rationale=%s",
                        request_id, request.session_id, request.provider, request.model, response.strategy, response.status, response.retry_count, response.timings.model_dump_json(), turn.rationale[:120],
                    )
                    return self._with_resolution_meta(response)
                except DataBackendError as exc:
                    logger.warning(
                        "ask_data_backend_failed request_id=%s session_id=%s provider=%s model=%s safe_error_code=%s",
                        request_id, request.session_id, request.provider, request.model, exc.code,
                    )
                    elapsed = round((perf_counter() - started) * 1000, 3)
                    provider = self.dependencies.provider_registry.resolve(request.provider, request.model)
                    answer = await explain_failure(
                        provider=provider,
                        question=request.question,
                        failure={"kind": "data_backend", "code": exc.code},
                        request_id=request_id,
                    )
                    return self._with_resolution_meta(
                        AskDataResponse(
                            request_id=request_id,
                            session_id=request.session_id,
                            status="ERROR",
                            provider=request.provider,
                            model=request.model,
                            strategy="unsupported",
                            answer=answer,
                            data=QueryData(), chart_spec=None, timings=Timings(total_ms=elapsed),
                        )
                    )
                except Exception:
                    logger.exception("ask_data_failed request_id=%s session_id=%s provider=%s model=%s", request_id, request.session_id, request.provider, request.model)
                    elapsed = round((perf_counter() - started) * 1000, 3)
                    provider = self.dependencies.provider_registry.resolve(request.provider, request.model)
                    answer = await explain_failure(
                        provider=provider,
                        question=request.question,
                        failure={"kind": "internal", "code": "UNEXPECTED"},
                        request_id=request_id,
                    )
                    return self._with_resolution_meta(
                        AskDataResponse(
                            request_id=request_id,
                            session_id=request.session_id,
                            status="ERROR",
                            provider=request.provider,
                            model=request.model,
                            strategy="unsupported",
                            answer=answer,
                            data=QueryData(), chart_spec=None, timings=Timings(total_ms=elapsed),
                        )
                    )
            finally:
                if isinstance(reg, HybridProviderRegistry):
                    reg.clear_request_context()

    async def stream(self, request: AskDataRequest):
        request_id = str(uuid.uuid4())
        start_request_usage(request_id)
        self._sync_runtime_for_request()
        self._active_resolution = None
        reg = self.dependencies.provider_registry
        if isinstance(reg, HybridProviderRegistry):
            reg.clear_request_context()
        async with self._prompt_resolution_scope():
            started = perf_counter()
            try:
                cap = "RAG_GENERATION" if request.mode == "rag" else "ASK_DATA"
                request = self._prepare_registry_request(request, capability=cap)
            except (RegistryRuntimeError, AiRegistryError) as exc:
                err = self._registry_error_response(request, request_id=request_id, exc=exc, started=started)
                yield {"type": "done", "response": self._with_resolution_meta(err)}
                return
            if request.mode == "rag":
                logger.info("ask_data_route=rag stream request_id=%s session_id=%s", request_id, request.session_id)
                try:
                    async for event in self._stream_rag(request, request_id=request_id):
                        if event.get("type") == "done":
                            event = {
                                **event,
                                "response": self._with_resolution_meta(event["response"]),
                            }
                        yield event
                finally:
                    if isinstance(reg, HybridProviderRegistry):
                        reg.clear_request_context()
                return
            conversation_history = self.history.load(request.session_id, limit=8)
            session_metric = _session_last_metric(conversation_history)
            session_ctx = analysis_context_from_history(conversation_history)
            turn = await self._understand_turn(request, conversation_history, request_id=request_id)
            question = resolve_question_for_pipeline(request.question, conversation_history, turn)
            precedence = self._structured_precedence(request, question=question)
            structured_resolution: dict[str, Any] | None = None
            if precedence is not None:
                if precedence.runtime_bundle is not None:
                    self.apply_runtime_bundle(precedence.runtime_bundle)
                if precedence.clarification is not None:
                    yield {
                        "type": "done",
                        "response": self._with_resolution_meta(
                            self._clarification_response(
                                request,
                                request_id=request_id,
                                payload=precedence.clarification,
                                started=started,
                            )
                        ),
                    }
                    return
                if precedence.explicit_error:
                    yield {
                        "type": "done",
                        "response": self._with_resolution_meta(
                            self._explicit_context_error_response(
                                request,
                                request_id=request_id,
                                message=precedence.explicit_error,
                                started=started,
                            )
                        ),
                    }
                    return
                if precedence.resolution is not None:
                    structured_resolution = precedence.resolution
            if structured_resolution is not None:
                route, resolution = "ossie", structured_resolution
            else:
                route, resolution = self._route_for_question(
                    question,
                    session_last_metric=session_metric,
                    session_analysis_context=session_ctx or None,
                    turn_understanding=turn,
                    conversation_history=conversation_history,
                )
            skip_v3 = (
                turn.is_conversational
                or resolution.get("status") == "history_only"
                or structured_resolution is not None
                or bool(structured_data_sources(request.context_sources))
            )
            if skip_v3:
                logger.info("ask_data_route=conversational stream request_id=%s session_id=%s", request_id, request.session_id)
            client = (
                None
                if skip_v3
                else self._v3_client()
                if route == "v3" and v3_agent_available(self.settings)
                else None
            )
            if client is not None:
                logger.info("ask_data_route=v3 stream request_id=%s session_id=%s", request_id, request.session_id)
                try:
                    async for event in client.stream_ask_data(
                        question,
                        session_id=request.session_id,
                        provider=request.provider,
                        model=request.model,
                        request_id=request_id,
                        answer_language="id",
                    ):
                        if event.get("type") == "progress":
                            yield {
                                "type": "progress",
                                "stage": event.get("stage") or "agent",
                                "label": event.get("label") or "Processing",
                                "detail": event.get("detail"),
                            }
                            continue
                        if event.get("type") == "done":
                            payload = event.get("response") or event
                            if isinstance(payload, dict) and "answer" in payload:
                                response = polish_v3_answer(
                                    _normalize_governed_v3_response(AskDataResponse.model_validate(payload))
                                )
                                response = self._attach_usage(request, response)
                                self._persist_turn(request, response, response.chart_spec)
                                yield {"type": "done", "response": response}
                            else:
                                yield event
                            return
                        if "request_id" in event and "answer" in event:
                            response = polish_v3_answer(
                                _normalize_governed_v3_response(AskDataResponse.model_validate(event))
                            )
                            response = self._attach_usage(request, response)
                            self._persist_turn(request, response, response.chart_spec)
                            yield {"type": "done", "response": response}
                            return
                    fallback = self._v3_fallback_to_ossie_on_error()
                    response = await self._run_via_tempo_agent_v3(
                        request, request_id=request_id, question=question, client=client
                    )
                    if response.status != "ERROR" or not fallback:
                        yield {"type": "done", "response": response}
                        return
                    logger.info("ask_data_v3_stream_fallback_ossie request_id=%s", request_id)
                except LocalAgentError:
                    if not self._v3_fallback_to_ossie_on_error():
                        response = await self._run_via_tempo_agent_v3(
                            request, request_id=request_id, question=question, client=client
                        )
                        yield {"type": "done", "response": response}
                        return
                    logger.info("ask_data_v3_stream_fallback_ossie request_id=%s", request_id)

            logger.info("ask_data_route=ossie stream request_id=%s session_id=%s", request_id, request.session_id)
            try:
                async for event in self._stream_ossie_workflow(
                    request,
                    request_id=request_id,
                    question=question,
                    resolution=resolution,
                    conversation_history=conversation_history,
                    session_analysis_context=session_ctx or None,
                    turn_understanding=turn,
                ):
                    if event.get("type") == "done":
                        event = {**event, "response": self._with_resolution_meta(event["response"])}
                    yield event
            finally:
                if isinstance(reg, HybridProviderRegistry):
                    reg.clear_request_context()
