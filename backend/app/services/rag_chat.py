from __future__ import annotations

import logging
import uuid
from time import perf_counter
from typing import AsyncIterator

from app.core.config import Settings
from app.core.models import AnalysisOutput, AskDataRequest, AskDataResponse, QueryData, RagRetrievalMeta, Timings
from app.db.platform_engine import get_session_factory
from app.llm.base import LLMProvider
from app.projects.resolver import load_default_project
from app.services.rag_service import RAGService

logger = logging.getLogger(__name__)

RAG_PROGRESS = (
    ("understand", "Understanding question"),
    ("retrieve", "Searching knowledge"),
    ("rerank", "Reviewing sources"),
    ("analyze", "Preparing answer"),
)


def _postgres_ready(settings: Settings) -> bool:
    from app.db.metadata_db import platform_metadata_configured

    return platform_metadata_configured(settings)


def _unsupported_message() -> AnalysisOutput:
    text = (
        "Knowledge RAG memerlukan STATE_STORE=postgres dan layanan dokumen aktif. "
        "Ask Data tetap tersedia tanpa knowledge."
    )
    return AnalysisOutput(
        direct_answer=text,
        executive_summary=text,
        insights=[],
        business_implications=[],
        caveats=[],
        data_reference="document knowledge unavailable",
        chart_spec=None,
    )


def _to_ask_data_response(
    request: AskDataRequest,
    *,
    request_id: str,
    result,
    started: float,
) -> AskDataResponse:
    elapsed = round((perf_counter() - started) * 1000, 3)
    exec_meta = result.execution_metadata or {}
    timings = Timings(
        context_ms=float(exec_meta.get("retrieval_ms") or 0),
        analysis_ms=float(exec_meta.get("llm_ms") or 0),
        total_ms=float(exec_meta.get("total_ms") or elapsed),
    )
    return AskDataResponse(
        request_id=request_id,
        session_id=request.session_id,
        status=result.status,  # type: ignore[arg-type]
        provider=request.provider,
        model=request.model,
        strategy="rag",
        route="rag",
        grounding=result.grounding,  # type: ignore[arg-type]
        answer=AnalysisOutput(
            direct_answer=result.answer_text,
            executive_summary=result.executive_summary,
            insights=result.insights,
            business_implications=result.business_implications,
            caveats=result.caveats,
            data_reference="retrieved document evidence",
            chart_spec=None,
        ),
        data=QueryData(),
        chart_spec=None,
        timings=timings,
        citations=result.citations or None,
        retrieval=RagRetrievalMeta(
            candidate_count=int(result.retrieval_meta.get("candidate_count") or 0),
            selected_count=int(result.retrieval_meta.get("selected_count") or 0),
        ),
    )


async def run_rag_turn(
    settings: Settings,
    request: AskDataRequest,
    *,
    request_id: str,
    conversation_history: list[dict],
    llm_provider: LLMProvider,
) -> tuple[AskDataResponse, dict]:
    started = perf_counter()
    if not _postgres_ready(settings):
        return (
            AskDataResponse(
                request_id=request_id,
                session_id=request.session_id,
                status="UNSUPPORTED",
                provider=request.provider,
                model=request.model,
                strategy="rag",
                route="rag",
                grounding="INSUFFICIENT_EVIDENCE",
                answer=_unsupported_message(),
                data=QueryData(),
                chart_spec=None,
                timings=Timings(total_ms=round((perf_counter() - started) * 1000, 3)),
            ),
            {},
        )

    project = load_default_project(settings)
    if not project:
        return (
            AskDataResponse(
                request_id=request_id,
                session_id=request.session_id,
                status="ERROR",
                provider=request.provider,
                model=request.model,
                strategy="rag",
                route="rag",
                grounding="INSUFFICIENT_EVIDENCE",
                answer=_unsupported_message(),
                data=QueryData(),
                chart_spec=None,
                timings=Timings(total_ms=round((perf_counter() - started) * 1000, 3)),
            ),
            {},
        )

    factory = get_session_factory(settings.database_url)
    with factory() as session:
        service = RAGService(settings)
        result = await service.rag_answer(
            session=session,
            query=request.question,
            workspace_id=uuid.UUID(str(project.workspace_id)),
            project_id=uuid.UUID(str(project.id)),
            library_ids=request.library_ids,
            document_ids=request.rag_document_ids,
            conversation_history=conversation_history,
            llm_provider=llm_provider,
        )
    response = _to_ask_data_response(request, request_id=request_id, result=result, started=started)
    logger.info(
        "rag_answer request_id=%s session_id=%s status=%s grounding=%s citations=%s total_ms=%s",
        request_id,
        request.session_id,
        response.status,
        response.grounding,
        len(response.citations or []),
        response.timings.total_ms,
    )
    return response, result.session_frame


async def stream_rag_turn(
    settings: Settings,
    request: AskDataRequest,
    *,
    request_id: str,
    conversation_history: list[dict],
    llm_provider: LLMProvider,
) -> AsyncIterator[dict]:
    for stage, label in RAG_PROGRESS[:3]:
        yield {"type": "progress", "stage": stage, "label": label, "detail": None}
    response, session_frame = await run_rag_turn(
        settings,
        request,
        request_id=request_id,
        conversation_history=conversation_history,
        llm_provider=llm_provider,
    )
    yield {"type": "progress", "stage": "analyze", "label": "Preparing answer", "detail": None}
    yield {"type": "done", "response": response, "session_frame": session_frame}
