from __future__ import annotations

import logging
import uuid
from time import perf_counter
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.models import AskDataRequest, AskDataResponse
from app.prompt_management.resolver import PromptResolver
from app.services.chat import ChatService
from app.services.rag_chat import run_rag_turn
from app.services.skill_service import SkillService, SkillServiceError
from app.skills.tool_registry import ToolRegistry
from app.skills.types import SkillExecutionContext

logger = logging.getLogger(__name__)


class SkillExecutionError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _handler_type(version) -> str:
    return str((version.config or {}).get("handler_type") or "prompt_only")


def _validate_input(version, user_input: str) -> None:
    schema = version.input_schema
    if not schema:
        return
    min_len = schema.get("minLength")
    if isinstance(min_len, int) and len(user_input.strip()) < min_len:
        raise SkillExecutionError("invalid_input", "Input too short", 422)


class SkillExecutionService:
    def __init__(
        self,
        settings: Settings,
        session: Session,
        *,
        chat_service: ChatService | None = None,
    ) -> None:
        self._settings = settings
        self._session = session
        self._chat = chat_service
        self._skills = SkillService(session)

    def build_context(
        self,
        skill_id: uuid.UUID,
        *,
        user_input: str,
        conversation_id: str | None,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        runtime_context: dict[str, Any] | None = None,
    ) -> SkillExecutionContext:
        version = self._skills.get_active_version(skill_id)
        skill = self._skills.get_skill(skill_id)
        if skill.workspace_id != workspace_id:
            raise SkillExecutionError("forbidden", "Skill workspace mismatch", 403)
        if skill.scope == "project" and skill.project_id != project_id:
            raise SkillExecutionError("forbidden", "Skill project mismatch", 403)

        _validate_input(version, user_input)
        handler = _handler_type(version)
        try:
            ToolRegistry.validate_handler_tools(handler, list(version.allowed_tools or []))
        except ValueError as exc:
            raise SkillExecutionError("invalid_tools", str(exc), 422) from exc

        effective_prompt = None
        if version.prompt_key:
            effective_prompt = PromptResolver(self._settings, session=self._session).resolve(
                version.prompt_key,
                workspace_id=workspace_id,
                project_id=project_id,
            )

        return SkillExecutionContext(
            skill=skill,
            version=version,
            workspace_id=workspace_id,
            project_id=project_id,
            user_input=user_input.strip(),
            conversation_id=conversation_id,
            resolved_prompt=effective_prompt,
            allowed_tools=list(version.allowed_tools or []),
            handler_type=handler,
            runtime_metadata=dict(runtime_context or {}),
        )

    async def execute(
        self,
        skill_id: uuid.UUID,
        *,
        user_input: str,
        conversation_id: str | None,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        runtime_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        started = perf_counter()
        ctx = self.build_context(
            skill_id,
            user_input=user_input,
            conversation_id=conversation_id,
            workspace_id=workspace_id,
            project_id=project_id,
            runtime_context=runtime_context,
        )
        tools_used: list[str] = []
        status = "SUCCESS"
        result: dict[str, Any]
        try:
            if ctx.handler_type == "ask_data":
                if "ask_data" not in ctx.allowed_tools:
                    raise SkillExecutionError("tool_denied", "ask_data not allowed for this skill", 403)
                tools_used.append("ask_data")
                result = await self._run_ask_data(ctx)
            elif ctx.handler_type == "rag":
                if not any(t in ctx.allowed_tools for t in ("rag_search", "document_retrieval")):
                    raise SkillExecutionError("tool_denied", "RAG tools not allowed for this skill", 403)
                tools_used.extend([t for t in ctx.allowed_tools if t in ("rag_search", "document_retrieval")])
                result = await self._run_rag(ctx)
            else:
                tools_used = []
                result = await self._run_prompt_only(ctx)
        except SkillExecutionError:
            raise
        except SkillServiceError as exc:
            raise SkillExecutionError(exc.code, exc.message, exc.status_code) from exc
        except Exception as exc:
            status = "ERROR"
            logger.warning("skill_execute_failed skill_id=%s err=%s", skill_id, type(exc).__name__)
            raise SkillExecutionError("execution_failed", "Skill execution failed", 500) from exc

        elapsed_ms = int((perf_counter() - started) * 1000)
        logger.info(
            "skill_execute skill_id=%s skill_version=%s handler_type=%s tools_used=%s project_id=%s execution_ms=%s status=%s",
            ctx.skill.id,
            ctx.version.version_number,
            ctx.handler_type,
            ",".join(tools_used),
            project_id,
            elapsed_ms,
            status,
        )
        prompt_source = ctx.resolved_prompt.source if ctx.resolved_prompt else None
        return {
            "status": status,
            "result": result,
            "execution": {
                "skill_id": str(ctx.skill.id),
                "skill_key": ctx.skill.key,
                "skill_version": ctx.version.version_number,
                "skill_version_id": str(ctx.version.id),
                "handler_type": ctx.handler_type,
                "tools_used": tools_used,
                "prompt_key": ctx.version.prompt_key,
                "prompt_source": prompt_source,
                "execution_ms": elapsed_ms,
            },
        }

    async def _run_ask_data(self, ctx: SkillExecutionContext) -> dict[str, Any]:
        if self._chat is None:
            raise SkillExecutionError("unavailable", "Chat service not configured", 503)
        provider = self._settings.default_llm_provider.strip().lower()
        if provider not in {"qwen", "gemini", "openai"}:
            provider = "gemini"
        model = self._settings.gemini_model if provider == "gemini" else self._settings.qwen_model
        request = AskDataRequest(
            session_id=ctx.conversation_id or str(uuid.uuid4()),
            question=ctx.user_input,
            provider=provider,  # type: ignore[arg-type]
            model=model or "gemini-3.8-flash",
            mode="ask_data",
        )
        response: AskDataResponse = await self._chat.run(request, force_ossie=True)
        return {
            "answer": response.answer.direct_answer,
            "executive_summary": response.answer.executive_summary,
            "status": response.status,
            "strategy": response.strategy,
        }

    async def _run_rag(self, ctx: SkillExecutionContext) -> dict[str, Any]:
        if self._chat is None:
            raise SkillExecutionError("unavailable", "Chat service not configured", 503)
        provider = self._settings.default_llm_provider.strip().lower()
        if provider not in {"qwen", "gemini", "openai"}:
            provider = "gemini"
        model = self._settings.gemini_model if provider == "gemini" else self._settings.qwen_model
        library_ids = ctx.runtime_metadata.get("library_ids")
        if library_ids is not None and not isinstance(library_ids, list):
            library_ids = None
        request = AskDataRequest(
            session_id=ctx.conversation_id or str(uuid.uuid4()),
            question=ctx.user_input,
            provider=provider,  # type: ignore[arg-type]
            model=model or "gemini-3.8-flash",
            mode="rag",
            library_ids=library_ids,
        )
        provider_impl = self._chat._resolve_provider(request, str(uuid.uuid4()))
        history: list[dict] = []
        if ctx.conversation_id:
            history = self._chat.history.load(ctx.conversation_id, limit=8)
        response, _frame = await run_rag_turn(
            self._settings,
            request,
            request_id=str(uuid.uuid4()),
            conversation_history=history,
            llm_provider=provider_impl,
        )
        return {
            "answer": response.answer.direct_answer,
            "executive_summary": response.answer.executive_summary,
            "status": response.status,
            "grounding": response.grounding,
            "citations_count": len(response.citations or []),
        }

    async def _run_prompt_only(self, ctx: SkillExecutionContext) -> dict[str, Any]:
        from pydantic import Field

        from app.ai_registry.hybrid_provider_registry import HybridProviderRegistry
        from app.ai_registry.runtime_errors import RegistryRuntimeError
        from app.core.models import StrictModel
        from app.llm.registry import ProviderRegistry

        class SkillTextOutput(StrictModel):
            answer: str = Field(min_length=1)

        provider_name = self._settings.default_llm_provider.strip().lower()
        if provider_name not in {"qwen", "gemini", "openai"}:
            provider_name = "gemini"
        model = self._settings.gemini_model if provider_name == "gemini" else self._settings.qwen_model
        if provider_name == "openai":
            model = self._settings.openai_model or model
        registry = None
        if self._chat is not None:
            registry = self._chat.dependencies.provider_registry
        if isinstance(registry, HybridProviderRegistry):
            try:
                registry.prepare_request(
                    capability="SKILLS",
                    workspace_id=ctx.workspace_id,
                    project_id=ctx.project_id,
                    fallback_provider=provider_name,
                    fallback_model=model or "gemini-3.8-flash",
                )
                provider = registry.resolve(provider_name, model or "gemini-3.8-flash")
            except RegistryRuntimeError as exc:
                raise SkillExecutionError(exc.code.lower(), exc.message, exc.status_code) from exc
            finally:
                registry.clear_request_context()
        else:
            provider = ProviderRegistry(self._settings).resolve(provider_name, model or "gemini-3.8-flash")

        system_parts: list[str] = []
        if ctx.resolved_prompt and ctx.resolved_prompt.content.strip():
            system_parts.append(ctx.resolved_prompt.content.strip())
        if ctx.version.instructions.strip():
            system_parts.append(ctx.version.instructions.strip())
        system = "\n\n".join(system_parts) or "You are a helpful assistant."
        out = await provider.generate_structured(
            [{"role": "system", "content": system}, {"role": "user", "content": ctx.user_input}],
            SkillTextOutput,
            temperature=0.2,
            max_tokens=min(self._settings.llm_max_tokens, 2048),
        )
        return {"answer": out.answer.strip()}
