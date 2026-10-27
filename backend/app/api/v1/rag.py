from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import default_project_context, postgres_session, require_postgres_settings
from app.core.config import Settings
from app.core.models import AskDataRequest
from app.rag.schemas import RagQueryRequest, RagQueryResponse
from app.services.rag_chat import run_rag_turn

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/query")
async def rag_query(
    body: RagQueryRequest,
    request: Request,
    session: Session = Depends(postgres_session),
    settings: Settings = Depends(require_postgres_settings),
    ctx=Depends(default_project_context),
) -> RagQueryResponse:
    workspace_id, default_project_id = ctx
    project_id = body.project_id or default_project_id
    if body.project_id and body.project_id != default_project_id:
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Project access denied"})

    legacy_registry = request.app.state.provider_registry
    model = body.model.strip() or next(
        (m.id for m in legacy_registry.list_models() if m.provider == body.provider and m.available),
        "",
    )
    if not model:
        raise HTTPException(status_code=503, detail={"code": "model_unavailable", "message": "No model available"})

    session_id = (body.conversation_id or str(uuid.uuid4())).strip()
    chat_request = AskDataRequest(
        session_id=session_id,
        question=body.query,
        provider=body.provider,  # type: ignore[arg-type]
        model=model,
        mode="rag",
        library_ids=[str(i) for i in body.library_ids] if body.library_ids else None,
    )
    request_id = str(uuid.uuid4())
    from app.llm.usage_context import attach_usage_tracker, start_request_usage
    from app.ai_registry.hybrid_provider_registry import HybridProviderRegistry
    from app.ai_registry.runtime_errors import RegistryRuntimeError

    chat_service = request.app.state.chat_service
    usage_tracker = getattr(chat_service, "usage_tracker", None)
    if usage_tracker is not None:
        attach_usage_tracker(usage_tracker)
    start_request_usage(request_id)
    hybrid = chat_service.dependencies.provider_registry
    try:
        if isinstance(hybrid, HybridProviderRegistry):
            chat_request = chat_service._prepare_registry_request(chat_request, capability="RAG_GENERATION")
            provider = hybrid.resolve(chat_request.provider, chat_request.model)
        else:
            provider = legacy_registry.resolve(chat_request.provider, chat_request.model)
    except RegistryRuntimeError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    finally:
        if isinstance(hybrid, HybridProviderRegistry):
            hybrid.clear_request_context()
    if usage_tracker is not None:
        provider = usage_tracker.wrap(provider, request_id)
    _ = session
    response, _ = await run_rag_turn(
        settings,
        chat_request,
        request_id=request_id,
        conversation_history=[],
        llm_provider=provider,
    )
    return RagQueryResponse(
        status=response.status.lower() if response.status else "error",
        answer=response.answer.direct_answer,
        grounding=response.grounding,
        citations=[c.model_dump() for c in (response.citations or [])],
        retrieval=response.retrieval.model_dump() if response.retrieval else {},
        execution_metadata={
            "total_ms": response.timings.total_ms,
            "retrieval_ms": response.timings.context_ms,
            "llm_ms": response.timings.analysis_ms,
        },
    )
