from __future__ import annotations

import logging
from contextlib import asynccontextmanager
import dataclasses
from dataclasses import dataclass
from time import perf_counter
from typing import Any
import uuid

from app.core.config import Settings
from app.core.language import detect_language
from app.core.models import (
    AnalysisOutput,
    AskDataClarification,
    AskDataRequest,
    AskDataResponse,
    ChartSpec,
    ClarificationOption,
    LlmUsage,
    ModelInfo,
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
from app.ask_data.legacy_executor import build_query_executor
from app.ask_data.validation import validate_ask_data_sql
from app.graph.workflow import WorkflowDependencies, build_workflow
from app.ai_registry.hybrid_provider_registry import HybridProviderRegistry
from app.ai_registry.errors import AiRegistryError
from app.ai_registry.runtime_errors import RegistryRuntimeError
from app.core.models import ModelResolutionMeta
from app.llm.registry import ProviderRegistry
from app.semantic.context import SemanticContextService
from app.ask_data.presentation_tier import attach_presentation_tier
from app.ask_data.presentation_tier_config import PresentationTierConfig
from app.workspace.presentation_config_resolver import load_presentation_tier_config
from app.ask_data.conversation import (
    TurnReading,
    pick_metric,
    last_metric,
    last_turn,
    looks_like_small_talk,
    read_turn,
    turn_memory,
    narrow_metric_options,
    comparison_follow_up,
)
from app.services.guardrails import out_of_scope_message, should_block_ask_data_scope
from app.services.ossie_trace import NODE_LABELS, trace_detail
from app.chat.context_sources import (
    ContextSourceError,
    apply_context_sources,
    mcp_connector_sources,
    structured_data_sources,
)
from app.mcp.service import run_mcp_turn
from app.ask_data.structured_context_resolver import StructuredAskPrecedence, resolve_structured_ask
from app.services.rag_chat import run_rag_turn, stream_rag_turn
from app.services.user_facing_error import explain_failure


logger = logging.getLogger(__name__)


@dataclass
class _PreparedTurn:
    """A question that is ready for the workflow, or the answer that ends the turn before it."""

    response: AskDataResponse | None = None
    question: str = ""
    resolution: dict[str, Any] | None = None
    history: list[dict[str, Any]] | None = None
    previous: dict[str, Any] | None = None
    reading: TurnReading | None = None


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
        self._active_presentation_config = PresentationTierConfig.from_settings(settings)
        # A turn the agent already read, kept for the normal pipeline when the agent does not answer it.
        self._readings: dict[tuple[str, str], TurnReading] = {}
        self.apply_runtime_bundle(SemanticRuntimeLoader.get(settings).get_bundle())

    def _presentation_tier_config(self) -> PresentationTierConfig:
        return self._active_presentation_config

    def _refresh_presentation_tier_config(self) -> None:
        workspace_id = self._project_scope[0] if self._project_scope else None
        self._active_presentation_config = load_presentation_tier_config(
            self.settings,
            session_factory=self.dependencies.session_factory,
            workspace_id=workspace_id,
        )

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
        from app.db.metadata_db import platform_metadata_configured

        if not platform_metadata_configured(self.settings):
            self.apply_runtime_bundle(SemanticRuntimeLoader.get(self.settings).get_bundle())
            return
        factory = get_session_factory(self.settings.database_url)
        model_key = (self.settings.semantic_default_model_key or "").strip()
        with factory() as session:
            from app.projects.scope import load_project_for_semantic_model_key

            project = (
                load_project_for_semantic_model_key(session, self.settings, model_key)
                if model_key
                else load_default_project(self.settings)
            )
            if project is None:
                self.apply_runtime_bundle(SemanticRuntimeLoader.get(self.settings).get_bundle())
                return
            self._project_scope = (str(project.workspace_id), str(project.id))
            SemanticRuntimeLoader._instance = None  # noqa: SLF001
            loader = SemanticRuntimeLoader.get(self.settings)
            bundle = loader.refresh(
                session,
                workspace_id=project.workspace_id,
                project_id=project.id,
                model_key=model_key or None,
            )
            if bundle.mode == "legacy":
                active = loader.load_first_active_runtime(
                    session,
                    workspace_id=project.workspace_id,
                    project_id=project.id,
                )
                if active is not None:
                    loader.swap_bundle(active)
                    bundle = active
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

    def _finalize_response(
        self,
        response: AskDataResponse,
        *,
        inquiry_brief: dict[str, Any] | None = None,
    ) -> AskDataResponse:
        response = attach_presentation_tier(
            response,
            inquiry_brief=inquiry_brief,
            config=self._presentation_tier_config(),
        )
        return self._with_resolution_meta(response)

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
        from app.db.metadata_db import platform_metadata_configured

        if not platform_metadata_configured(self.settings):
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

    def assigned_model(self, mode: str = "ask_data") -> ModelInfo | None:
        """The model the project assigned to this kind of question in Settings -> AI Models, as the provider and model id
        the UI can send. None when nothing is assigned (the models configured by environment variables are then used)."""
        reg = self.dependencies.provider_registry
        if not isinstance(reg, HybridProviderRegistry):
            return None
        probe = AskDataRequest(session_id="model-probe", question="model", provider="qwen", model="model", mode="rag" if mode == "rag" else "ask_data")
        try:
            self._prepare_registry_request(probe, capability="RAG_GENERATION" if mode == "rag" else "ASK_DATA")
            resolution = reg.last_resolution
        except Exception:  # noqa: BLE001 - a disabled or broken assignment is reported when the model runs
            return None
        finally:
            reg.clear_request_context()
        if resolution is None or not resolution.uses_registry or not resolution.legacy_provider or not resolution.legacy_model:
            return None
        return ModelInfo(
            provider=resolution.legacy_provider,  # type: ignore[arg-type]
            id=resolution.legacy_model,
            label=resolution.model_key or resolution.legacy_model,
            available=True,
            assigned=True,
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


    def _structured_precedence(
        self,
        request: AskDataRequest,
        *,
        question: str,
        session_analysis_context: dict[str, Any] | None = None,
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
        with self.dependencies.session_factory() as session:
            from app.projects.scope import resolve_structured_project_scope

            project = resolve_structured_project_scope(session, self.settings, request)
            if project is None:
                return None
            self._project_scope = (str(project.workspace_id), str(project.id))
            return resolve_structured_ask(
                session,
                settings=self.settings,
                workspace_id=project.workspace_id,
                project_id=project.id,
                request=request,
                semantic_context=self.dependencies.semantic_context,
                question=question,
                session_analysis_context=session_analysis_context,
            )

    @staticmethod
    def _skip_structured_clarification(turn: TurnReading, raw_question: str) -> bool:
        """Greeting / capability turns must not be short-circuited by structured metric clarification."""
        return turn.is_conversational or looks_like_small_talk(raw_question)

    @staticmethod
    def _ignore_structured_explicit_error(
        turn: TurnReading,
        question: str,
        precedence: StructuredAskPrecedence,
    ) -> bool:
        if not precedence.explicit_error or precedence.runtime_bundle is None:
            return False
        return turn.is_conversational or looks_like_small_talk(question)


    def _ask_data_space_instructions(self) -> str:
        factory = self.dependencies.session_factory
        scope = self._project_scope
        if factory is None or not scope:
            return ""
        try:
            workspace_id = uuid.UUID(scope[0])
            project_id = uuid.UUID(scope[1])
        except ValueError:
            return ""
        from app.db.platform_models import SemanticVersionRow, WorkspaceRow
        from app.prompt_management.resolver import resolve_prompt_text
        from app.workspace.ask_data_settings import read_ask_data_settings
        from app.workspace.semantic_knowledge import read_semantic_knowledge

        parts: list[str] = []
        with factory() as session:
            row = session.get(WorkspaceRow, workspace_id)
            if row is None:
                return ""
            settings = read_ask_data_settings(row.settings_json)
            key = (settings.instruction_prompt_key or "").strip()
            if key:
                try:
                    parts.append(
                        resolve_prompt_text(
                            self.settings, key, session=session, workspace_id=workspace_id, project_id=project_id
                        ).strip()[:4000]
                    )
                except Exception:
                    pass
            version_id = getattr(self._runtime_meta, "semantic_version_id", None)
            if version_id:
                try:
                    version = session.get(SemanticVersionRow, uuid.UUID(str(version_id)))
                except ValueError:
                    version = None
                if version is not None:
                    knowledge = read_semantic_knowledge(row.settings_json, str(version.semantic_model_id))
                    if knowledge.instructions.strip():
                        parts.append("Instructions for this semantic model:\n" + knowledge.instructions.strip())
                    if knowledge.examples:
                        shown = "\n".join(f"- {example.question}" for example in knowledge.examples[:8])
                        parts.append("Example questions this model is expected to answer:\n" + shown)
        return "\n\n".join(part for part in parts if part)[:6000]

    def _capability_starter_questions(self) -> list[str]:
        factory = self.dependencies.session_factory
        scope = self._project_scope
        if factory is None or not scope:
            return []
        try:
            workspace_id = uuid.UUID(scope[0])
        except ValueError:
            return []
        from app.db.platform_models import WorkspaceRow
        from app.workspace.ask_data_settings import read_ask_data_settings

        with factory() as session:
            row = session.get(WorkspaceRow, workspace_id)
            if row is None:
                return []
            settings = read_ask_data_settings(row.settings_json)
        if settings.starter_source != "configured":
            return []
        return list(settings.starter_questions or [])

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
                caveats=[],
                data_reference="clarification_required",
                chart_spec=None,
            ),
            data=QueryData(),
            chart_spec=None,
            timings=Timings(total_ms=elapsed),
            clarification=AskDataClarification(reason=payload.reason, message=message, options=options),
        )

    def _out_of_scope_response(
        self,
        request: AskDataRequest,
        *,
        request_id: str,
        started: float,
    ) -> AskDataResponse:
        from time import perf_counter

        elapsed = round((perf_counter() - started) * 1000, 3) if started else 0.0
        text = out_of_scope_message()
        return AskDataResponse(
            request_id=request_id,
            session_id=request.session_id,
            status="UNSUPPORTED",
            provider=request.provider,
            model=request.model,
            strategy="unsupported",
            answer=AnalysisOutput(
                direct_answer=text,
                executive_summary=text,
                insights=[],
                business_implications=[],
                caveats=[],
                data_reference="ask_data_scope",
                chart_spec=None,
            ),
            data=QueryData(),
            chart_spec=None,
            timings=Timings(total_ms=elapsed),
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


    def _resolve_question(self, question: str, previous: dict[str, Any] | None) -> dict[str, Any]:
        return self.dependencies.semantic_context.resolve(question, session_analysis_context=previous)

    def _session_frame_for_turn(
        self,
        request: AskDataRequest,
        response: AskDataResponse,
        workflow_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = workflow_state or {}
        resolution = state.get("semantic_resolution") or {}
        metric = resolution.get("metric")
        dimensions = resolution.get("dimensions")
        scope = getattr(response.calculation, "scope", None) if response.calculation else None
        return turn_memory(
            question=request.question,
            standalone_question=str(state.get("question") or request.question),
            status=response.status,
            strategy=response.strategy,
            metric=str(metric) if isinstance(metric, str) else None,
            dimensions=[str(item) for item in dimensions] if isinstance(dimensions, list) else None,
            scope=scope,
            period=getattr(response.calculation, "period", None) if response.calculation else None,
        )


    def provider_for(self, request: AskDataRequest) -> tuple[AskDataRequest, Any]:
        """The request with its model resolved (registry assignment or legacy choice) and the provider to call."""
        prepared = self._prepare_registry_request(request, capability="ASK_DATA")
        return prepared, self.dependencies.provider_registry.resolve(prepared.provider, prepared.model)

    def metric_catalog(self) -> list[dict[str, Any]]:
        try:
            return list(self.dependencies.semantic_context.registry.metric_catalog_for_classification())
        except Exception:
            return []

    def ready_library_ids(self) -> list[str]:
        """Knowledge libraries that hold at least one document, for steps that look something up in the documents."""
        factory = self.dependencies.session_factory
        scope = self._project_scope
        if factory is None or not scope:
            return []
        try:
            from app.services.library_service import LibraryService

            with factory() as session:
                items = LibraryService(session).list_libraries(workspace_id=uuid.UUID(scope[0]), project_id=uuid.UUID(scope[1]))
            return [str(item.id) for item in items if int(getattr(item, "document_count", 0) or 0) > 0]
        except Exception:
            logger.exception("ready_library_ids_failed")
            return []

    def finalize_response(self, response: AskDataResponse) -> AskDataResponse:
        return self._finalize_response(response)

    def record_turn(self, request: AskDataRequest, response: AskDataResponse, *, frame: dict[str, Any] | None = None) -> None:
        """Keep an agent answer in the session history so follow-up questions can refer to it. `frame` is what the turn
        leaves behind (the metric and breakdown of the step whose table is shown), so "and per carrier?" still works."""
        self._persist_turn(request, response, response.chart_spec, session_frame_override=frame or None)

    def step_frame(self, session_id: str) -> dict[str, Any] | None:
        """The turn memory an agent step left in its own session, which is then removed."""
        try:
            entries = self.history.load(session_id, limit=1)
        except Exception:
            return None
        frame = entries[-1].get("session_frame") if entries and isinstance(entries[-1], dict) else None
        try:
            self.history.delete_session(session_id)
        except Exception:
            pass
        return dict(frame) if isinstance(frame, dict) else None

    async def read_conversation(self, request: AskDataRequest) -> tuple[TurnReading, list[dict[str, Any]]]:
        """The question read in the light of the conversation, for the agent. The reading is kept so the normal
        pipeline reuses it when the agent does not answer."""
        self._sync_runtime_for_request()
        history = self.history.load(request.session_id, limit=8)
        reading = await read_turn(
            provider=self.dependencies.provider_registry.resolve(request.provider, request.model),
            question=request.question,
            history=history,
            semantic_context=self.dependencies.semantic_context,
        )
        reading = self._guard_rewrite(request.question, reading, last_turn(history))
        if len(self._readings) > 256:
            self._readings.clear()
        self._readings[(request.session_id, request.question.strip())] = reading
        return reading, history

    def discard_reading(self, request: AskDataRequest) -> None:
        self._readings.pop((request.session_id, request.question.strip()), None)

    def settle_follow_ups(
        self, analysis: AnalysisOutput, *, asked: str, metric: str | None, dimensions: list[str] | None
    ) -> AnalysisOutput:
        """Only suggestions that can be answered when clicked, filled from the model itself (as for a normal answer)."""
        from app.graph.workflow import _settled_follow_ups

        return _settled_follow_ups(analysis, self.dependencies, asked=asked, metric=metric, dimensions=dimensions)

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

    async def _run_mcp(self, request: AskDataRequest, *, request_id: str) -> AskDataResponse:
        started = perf_counter()
        sources = mcp_connector_sources(request.context_sources) or []
        if not sources:
            raise ContextSourceError("invalid_context", "MCP mode requires an @ MCP connector chip", 422)
        connector_id = (sources[0].id or "").strip()
        workspace_json: dict | None = None
        factory = self.dependencies.session_factory
        scope = self._project_scope
        if factory and scope:
            try:
                from app.db.platform_models import WorkspaceRow

                ws_id = uuid.UUID(scope[0])
                with factory() as session:
                    row = session.get(WorkspaceRow, ws_id)
                    workspace_json = row.settings_json if row else None
            except ValueError:
                workspace_json = None
        provider = None
        try:
            prepared = self._prepare_registry_request(request, capability="ASK_DATA")
            provider = self.dependencies.provider_registry.resolve(prepared.provider, prepared.model)
        except Exception as exc:  # noqa: BLE001 - without a model the tool still runs and its raw result is shown
            logger.info("mcp_llm_unavailable request_id=%s reason=%s", request_id, type(exc).__name__)
        try:
            answer, _meta = await run_mcp_turn(
                self.settings,
                workspace_settings_json=workspace_json,
                connector_id=connector_id,
                question=request.question,
                provider=provider,
            )
        except ValueError as exc:
            elapsed = round((perf_counter() - started) * 1000, 3)
            text = str(exc)
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
                    caveats=[],
                    data_reference=f"mcp:{connector_id}",
                    chart_spec=None,
                ),
                data=QueryData(),
                chart_spec=None,
                timings=Timings(total_ms=elapsed),
            )
        elapsed = round((perf_counter() - started) * 1000, 3)
        response = AskDataResponse(
            request_id=request_id,
            session_id=request.session_id,
            status="SUCCESS",
            provider=request.provider,
            model=request.model,
            strategy="mcp",
            route="ask_data",
            answer=AnalysisOutput(
                direct_answer=answer,
                executive_summary=answer[:500],
                insights=[],
                business_implications=[],
                caveats=[],
                data_reference=f"mcp:{connector_id}",
                chart_spec=None,
            ),
            data=QueryData(),
            chart_spec=None,
            timings=Timings(total_ms=elapsed),
        )
        response = self._attach_usage(request, response)
        self._persist_turn(request, response, None)
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


    async def _read_turn(
        self,
        request: AskDataRequest,
        conversation_history: list[dict],
        *,
        request_id: str,
    ) -> TurnReading:
        kept = self._readings.pop((request.session_id, request.question.strip()), None)
        if kept is not None:
            return kept
        return await read_turn(
            provider=self._resolve_provider(request, request_id),
            question=request.question,
            history=conversation_history,
            semantic_context=self.dependencies.semantic_context,
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
        turn_reading: TurnReading | None = None,
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
            "session_last_metric": last_metric(conversation_history),
            "request_id": request_id,
            "retry_count": 0,
            "timings": {},
        }
        if turn_reading is not None:
            state["turn_reading"] = turn_reading.model_dump()
        if session_analysis_context:
            state["session_analysis_context"] = session_analysis_context
        starters = self._capability_starter_questions()
        if starters:
            state["capability_starter_questions"] = starters
        space_instructions = self._ask_data_space_instructions()
        if space_instructions:
            state["ask_data_space_instructions"] = space_instructions
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
            definition = resolution.get("definition") if isinstance(resolution.get("definition"), dict) else None
            if definition is None:
                try:
                    definition = self.dependencies.semantic_context.metric_definition(str(governed_metric))
                except Exception:
                    definition = None
            if isinstance(definition, dict):
                expr = str(definition.get("expression") or "").strip()
                if expr:
                    raw_data["governed_metric_expression"] = expr[:500]
                base = definition.get("base_dataset")
                if base:
                    raw_data["governed_base_dataset"] = str(base)
                ai_ctx = definition.get("ai_context") if isinstance(definition.get("ai_context"), dict) else {}
                display = (ai_ctx or {}).get("display_name") or definition.get("description")
                if display:
                    raw_data["governed_metric_display_name"] = str(display).strip()[:200]
        if unit_format:
            raw_data["unit_format"] = str(unit_format)
        try:
            from app.ask_data.column_labels import column_labels
            from app.ask_data.metric_labels import humanize_metric_label

            metric_label = None
            if governed_metric:
                try:
                    metric_label = humanize_metric_label(
                        name=str(governed_metric), definition=self.dependencies.semantic_context.metric_definition(str(governed_metric))
                    )
                except Exception:
                    metric_label = None
            raw_data["column_labels"] = column_labels(
                list(raw_data.get("columns") or []),
                semantic_context=self.dependencies.semantic_context,
                sql=str(state.get("validated_sql") or state.get("sql") or ""),
                metric_label=metric_label,
            )
        except Exception:
            logger.exception("column_labels_failed request_id=%s", request_id)
        if isinstance(state.get("overall_value"), (int, float)):
            raw_data["overall_value"] = float(state["overall_value"])
        if isinstance(state.get("data_coverage"), dict):
            raw_data["data_coverage"] = dict(state["data_coverage"])
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
        inquiry_brief = state.get("inquiry_brief") if isinstance(state.get("inquiry_brief"), dict) else None
        calculation = None
        if state.get("status") == "SUCCESS":
            from app.ask_data.calculation_note import build_calculation_note

            note_definition = resolution.get("definition") if isinstance(resolution.get("definition"), dict) else None
            if note_definition is None and governed_metric:
                try:
                    note_definition = self.dependencies.semantic_context.metric_definition(str(governed_metric))
                except Exception:
                    note_definition = None
            try:
                calculation = build_calculation_note(
                    strategy=str(state.get("strategy") or ""),
                    sql=governed_sql,
                    metric=str(governed_metric) if governed_metric else None,
                    definition=note_definition,
                    dimensions=[str(d) for d in (resolution.get("dimensions") or [])],
                    drill=state.get("drill_across") if isinstance(state.get("drill_across"), dict) else None,
                    language=detect_language(str(state.get("question") or "")),
                    checks=state.get("verification_checks") or None,
                )
            except Exception:
                logger.exception("calculation_note_failed request_id=%s", request_id)
        response = AskDataResponse(
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
            calculation=calculation,
        )
        return attach_presentation_tier(
            response,
            inquiry_brief=inquiry_brief,
            config=self._presentation_tier_config(),
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
        turn_reading: TurnReading | None = None,
    ):
        started = perf_counter()
        initial = self._build_initial_state(
            request,
            request_id=request_id,
            question=question,
            resolution=resolution,
            conversation_history=conversation_history,
            session_analysis_context=session_analysis_context,
            turn_reading=turn_reading,
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

    async def _prepare_turn(self, request: AskDataRequest, *, request_id: str, started: float) -> _PreparedTurn:
        """Everything between the question and the workflow: read it in the light of the conversation, check its
        scope, apply an explicit @ context and resolve it to a governed metric."""
        history = self.history.load(request.session_id, limit=8)
        previous = last_turn(history)
        reading = await self._read_turn(request, history, request_id=request_id)
        reading = self._guard_rewrite(request.question, reading, previous)
        reading = self._comparison_follow_up(request.question, reading, previous)
        question = reading.standalone_question or request.question
        if not reading.is_conversational and should_block_ask_data_scope(
            question, raw_question=request.question, history=history
        ):
            return _PreparedTurn(response=self._out_of_scope_response(request, request_id=request_id, started=started))
        # A rewritten question already carries what it needs from the previous turn; the previous metric is only the
        # safety net for a question the model could not rewrite.
        carry = None if reading.uses_previous else previous
        precedence = self._structured_precedence(request, question=question, session_analysis_context=carry)
        resolution: dict[str, Any] | None = None
        if precedence is not None:
            if precedence.runtime_bundle is not None:
                self.apply_runtime_bundle(precedence.runtime_bundle)
            skip = self._skip_structured_clarification(reading, request.question)
            if precedence.clarification is not None and not skip and precedence.clarification.reason == "metric_ambiguous" and precedence.runtime_bundle is not None:
                settled, narrowed = await self._settle_metric_choice(
                    request, request_id=request_id, question=question, ctx=precedence.runtime_bundle.context, payload=precedence.clarification,
                    continued=previous if reading.uses_previous else None,
                )
                if settled is not None:
                    resolution = settled
                    precedence = dataclasses.replace(precedence, clarification=None, resolution=settled)
                elif narrowed is not None:
                    precedence = dataclasses.replace(precedence, clarification=narrowed)
            if precedence.clarification is not None and not skip:
                return _PreparedTurn(
                    response=self._clarification_response(
                        request, request_id=request_id, payload=precedence.clarification, started=started
                    )
                )
            if precedence.explicit_error and not self._ignore_structured_explicit_error(reading, question, precedence):
                return _PreparedTurn(
                    response=self._explicit_context_error_response(
                        request, request_id=request_id, message=precedence.explicit_error, started=started
                    )
                )
            if precedence.resolution is not None and not skip:
                resolution = precedence.resolution
                if resolution.get("status") == "needs_clarification":
                    from app.ask_data.structured_context_resolver import _clarification_from_resolution

                    payload = _clarification_from_resolution(resolution)
                    if payload is not None:
                        return _PreparedTurn(
                            response=self._clarification_response(
                                request, request_id=request_id, payload=payload, started=started
                            )
                        )
        self._refresh_presentation_tier_config()
        if resolution is None:
            resolution = self._resolve_question(question, carry)
            if (
                not reading.is_conversational
                and resolution.get("status") == "needs_clarification"
                and resolution.get("reason") == "metric_ambiguous"
            ):
                from app.ask_data.structured_context_resolver import _clarification_from_resolution

                payload = _clarification_from_resolution(resolution)
                settled, narrowed = await self._settle_metric_choice(
                    request, request_id=request_id, question=question, ctx=self.dependencies.semantic_context, payload=payload,
                    continued=previous if reading.uses_previous else None,
                )
                if settled is not None:
                    resolution = settled
                elif payload is not None:
                    return _PreparedTurn(
                        response=self._clarification_response(request, request_id=request_id, payload=narrowed or payload, started=started)
                    )
        logger.info(
            "ask_data_turn request_id=%s session_id=%s kind=%s uses_previous=%s resolution=%s metric=%s",
            request_id,
            request.session_id,
            reading.kind,
            reading.uses_previous,
            resolution.get("status"),
            resolution.get("metric"),
        )
        return _PreparedTurn(
            question=question, resolution=resolution, history=history, previous=carry, reading=reading
        )

    def _comparison_follow_up(self, raw: str, reading: TurnReading, previous: dict[str, Any] | None) -> TurnReading:
        """A comparison that names one month continues the last turn's month: written out in full when the rewrite did
        not already make it a two-period comparison."""
        if reading.is_conversational or not previous:
            return reading
        from app.ask_data.comparisons import detect_period_comparison
        from app.ask_data.metric_labels import humanize_metric_label

        if reading.uses_previous and detect_period_comparison(reading.standalone_question):
            return reading
        metric = str(previous.get("last_metric") or "")
        ctx = self.dependencies.semantic_context
        try:
            label = humanize_metric_label(name=metric, definition=ctx.metric_definition(metric)) if metric in ctx.metrics else None
        except Exception:
            label = None
        written = comparison_follow_up(raw, previous, label)
        if not written:
            return reading
        logger.info("comparison_follow_up question=%r standalone=%r", raw[:200], written)
        return TurnReading(kind="data", uses_previous=True, standalone_question=written, rationale="comparison_follow_up")

    def _guard_rewrite(self, raw: str, reading: TurnReading, previous: dict[str, Any] | None) -> TurnReading:
        """A follow-up that names no metric of its own continues the last turn's metric. A rewrite that switched to
        another metric took the wrong turn ("kalau Juni?" after orders, rewritten as a late rate) and is not used."""
        if not reading.uses_previous or not previous or not previous.get("last_metric"):
            return reading
        registry = self.dependencies.semantic_context.registry
        try:
            if registry.resolve_metric(raw).get("status") == "resolved":
                return reading
            rewritten = registry.resolve_metric(reading.standalone_question)
        except Exception:
            return reading
        if rewritten.get("status") == "resolved" and rewritten.get("metric") != previous["last_metric"]:
            logger.info(
                "conversation_rewrite_rejected reason=switched_metric last=%s rewritten=%s", previous["last_metric"], rewritten.get("metric")
            )
            return TurnReading(kind="data", uses_previous=False, standalone_question=raw.strip(), rationale="rewrite_switched_metric")
        return reading

    async def _settle_metric_choice(
        self,
        request: AskDataRequest,
        *,
        request_id: str,
        question: str,
        ctx: Any,
        payload: Any,
        continued: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, Any]:
        """The language model reads an ambiguous question against the catalog. A sure pick becomes the resolution;
        otherwise the choice offered to the user is narrowed to the metrics that could fit.

        A follow-up that continues the previous turn ("kalau per carrier?") keeps that turn's metric: the rewrite may
        describe it in other words ("tingkat keterlambatan"), which is no reason to ask which metric was meant."""
        kept = (continued or {}).get("last_metric")
        if isinstance(kept, str) and kept in getattr(ctx, "metrics", {}):
            logger.info("metric_kept_from_previous_turn metric=%s", kept)
            try:
                return {**ctx.resolve_for_metric(question, kept), "context_mode": "GOVERNED_SEMANTIC"}, None
            except Exception:
                logger.exception("metric_keep_failed metric=%s", kept)
        pick = await pick_metric(provider=self._resolve_provider(request, request_id), question=question, semantic_context=ctx)
        if pick.metric:
            try:
                resolution = ctx.resolve_for_metric(question, pick.metric)
            except Exception:
                logger.exception("metric_choice_resolve_failed metric=%s", pick.metric)
                return None, None
            return {**resolution, "context_mode": "GOVERNED_SEMANTIC"}, None
        if payload is None or not pick.candidates:
            return None, None
        narrowed = narrow_metric_options(payload.options, pick.candidates, ctx)
        if not narrowed:
            return None, None
        return None, dataclasses.replace(payload, options=narrowed)

    def _failure_response(self, request: AskDataRequest, *, request_id: str, answer: AnalysisOutput, started: float) -> AskDataResponse:
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
            timings=Timings(total_ms=round((perf_counter() - started) * 1000, 3)),
        )

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
            if request.mode == "mcp":
                logger.info("ask_data_route=mcp request_id=%s session_id=%s", request_id, request.session_id)
                out = await self._run_mcp(request, request_id=request_id)
                return self._finalize_response(out)
            try:
                cap = "RAG_GENERATION" if request.mode == "rag" else "ASK_DATA"
                request = self._prepare_registry_request(request, capability=cap)
            except (RegistryRuntimeError, AiRegistryError) as exc:
                logger.warning(
                    "model_resolution_failed request_id=%s capability=%s code=%s", request_id, cap, exc.code
                )
                return self._registry_error_response(request, request_id=request_id, exc=exc, started=started)
            try:
                if request.mode == "rag":
                    logger.info("ask_data_route=rag request_id=%s session_id=%s", request_id, request.session_id)
                    out = await self._run_rag(request, request_id=request_id)
                    return self._finalize_response(out)
                prepared = await self._prepare_turn(request, request_id=request_id, started=started)
                if prepared.response is not None:
                    return self._finalize_response(prepared.response)
                initial = self._build_initial_state(
                    request,
                    request_id=request_id,
                    question=prepared.question,
                    resolution=prepared.resolution or {},
                    conversation_history=prepared.history or [],
                    session_analysis_context=prepared.previous,
                    turn_reading=prepared.reading,
                )
                try:
                    state = await self.workflow.ainvoke(initial)
                    response = self._response_from_state(request, request_id=request_id, state=state, started=started)
                    response = self._attach_usage(request, response)
                    self._persist_turn(request, response, response.chart_spec, workflow_state=state)
                    logger.info(
                        "ask_data request_id=%s session_id=%s provider=%s model=%s strategy=%s status=%s retry_count=%s timings=%s",
                        request_id, request.session_id, request.provider, request.model, response.strategy, response.status, response.retry_count, response.timings.model_dump_json(),
                    )
                    return self._finalize_response(response)
                except DataBackendError as exc:
                    logger.warning(
                        "ask_data_backend_failed request_id=%s session_id=%s provider=%s model=%s safe_error_code=%s",
                        request_id, request.session_id, request.provider, request.model, exc.code,
                    )
                    provider = self.dependencies.provider_registry.resolve(request.provider, request.model)
                    answer = await explain_failure(
                        provider=provider,
                        question=request.question,
                        failure={"kind": "data_backend", "code": exc.code},
                        request_id=request_id,
                    )
                    return self._finalize_response(self._failure_response(request, request_id=request_id, answer=answer, started=started))
                except Exception:
                    logger.exception("ask_data_failed request_id=%s session_id=%s provider=%s model=%s", request_id, request.session_id, request.provider, request.model)
                    provider = self.dependencies.provider_registry.resolve(request.provider, request.model)
                    answer = await explain_failure(
                        provider=provider,
                        question=request.question,
                        failure={"kind": "internal", "code": "UNEXPECTED"},
                        request_id=request_id,
                    )
                    return self._finalize_response(self._failure_response(request, request_id=request_id, answer=answer, started=started))
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
            if request.mode == "mcp":
                logger.info("ask_data_route=mcp stream request_id=%s session_id=%s", request_id, request.session_id)
                try:
                    out = await self._run_mcp(request, request_id=request_id)
                    yield {"type": "done", "response": self._finalize_response(out)}
                finally:
                    if isinstance(reg, HybridProviderRegistry):
                        reg.clear_request_context()
                return
            try:
                cap = "RAG_GENERATION" if request.mode == "rag" else "ASK_DATA"
                request = self._prepare_registry_request(request, capability=cap)
            except (RegistryRuntimeError, AiRegistryError) as exc:
                err = self._registry_error_response(request, request_id=request_id, exc=exc, started=started)
                yield {"type": "done", "response": self._finalize_response(err)}
                return
            try:
                if request.mode == "rag":
                    logger.info("ask_data_route=rag stream request_id=%s session_id=%s", request_id, request.session_id)
                    async for event in self._stream_rag(request, request_id=request_id):
                        if event.get("type") == "done":
                            event = {**event, "response": self._finalize_response(event["response"])}
                        yield event
                    return
                prepared = await self._prepare_turn(request, request_id=request_id, started=started)
                if prepared.response is not None:
                    yield {"type": "done", "response": self._finalize_response(prepared.response)}
                    return
                logger.info("ask_data_route=ossie stream request_id=%s session_id=%s", request_id, request.session_id)
                async for event in self._stream_ossie_workflow(
                    request,
                    request_id=request_id,
                    question=prepared.question,
                    resolution=prepared.resolution or {},
                    conversation_history=prepared.history or [],
                    session_analysis_context=prepared.previous,
                    turn_reading=prepared.reading,
                ):
                    if event.get("type") == "done":
                        event = {**event, "response": self._finalize_response(event["response"])}
                    yield event
            finally:
                if isinstance(reg, HybridProviderRegistry):
                    reg.clear_request_context()
