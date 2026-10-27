from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.llm.base import LLMProvider
from app.rag.citations_util import citation_records, citations_from_evidence, validate_cited_ids
from app.rag.models import RagLlmOutput
from app.rag.prompt import build_rag_user_message, load_rag_insufficient_message, load_rag_system_prompt
from app.rag.scope import bounded_rag_dialog, build_rag_session_frame, resolve_library_ids
from app.retrieval.types import RetrievalCandidate
from app.services.retrieval_service import RetrievalService, RetrievalServiceError

logger = logging.getLogger(__name__)


def normalize_rag_llm_output(llm_out: RagLlmOutput) -> tuple[str, str, list[str], list[str], list[str]]:
    """Default RAG replies are one prose block; fold legacy section fields into direct_answer."""
    answer = llm_out.direct_answer.strip()
    summary = (llm_out.executive_summary or "").strip()
    insights = [item.strip() for item in llm_out.insights if (item or "").strip()]
    implications = [item.strip() for item in llm_out.business_implications if (item or "").strip()]
    caveats = list(llm_out.caveats)

    extras: list[str] = []
    if summary and summary != answer and summary not in answer:
        extras.append(summary)
    for item in insights + implications:
        if item not in answer:
            extras.append(item)
    if extras:
        answer = f"{answer}\n\n" + "\n\n".join(extras) if answer else "\n\n".join(extras)
    summary = answer
    return answer, summary, [], [], caveats


@dataclass
class RagAnswerResult:
    grounding: str
    answer_text: str
    executive_summary: str
    insights: list[str]
    caveats: list[str]
    business_implications: list[str]
    citations: list
    retrieval_meta: dict
    execution_metadata: dict
    session_frame: dict
    status: str


class RAGService:
    def __init__(
        self,
        settings: Settings,
        *,
        retrieval: RetrievalService | None = None,
    ) -> None:
        self._settings = settings
        self._retrieval_factory = retrieval

    def _default_libraries(self) -> list[str]:
        raw = (self._settings.rag_default_library_ids or "").strip()
        if not raw:
            return []
        return [part.strip() for part in raw.split(",") if part.strip()]

    def _retrieval(self, session: Session) -> RetrievalService:
        if self._retrieval_factory is not None:
            return self._retrieval_factory
        return RetrievalService(self._settings, session)

    def _top_score(self, results: list[RetrievalCandidate]) -> float:
        if not results:
            return 0.0
        best = results[0]
        if best.rerank_score is not None:
            return float(best.rerank_score)
        return float(best.vector_score)

    def _insufficient_result(
        self,
        *,
        message: str,
        retrieval_payload: dict | None,
        library_ids: list[uuid.UUID],
        project_id: uuid.UUID,
        started: float,
    ) -> RagAnswerResult:
        meta = (retrieval_payload or {}).get("metadata") or {}
        ctx = (retrieval_payload or {}).get("context") or {}
        elapsed = int((time.perf_counter() - started) * 1000)
        return RagAnswerResult(
            grounding="INSUFFICIENT_EVIDENCE",
            answer_text=message,
            executive_summary=message,
            insights=[],
            caveats=["Tidak ada bukti dokumen yang cukup untuk jawaban ter-grounding."],
            business_implications=[],
            citations=[],
            retrieval_meta={
                "candidate_count": int(ctx.get("total_candidates") or 0),
                "selected_count": int(ctx.get("selected_candidates") or 0),
            },
            execution_metadata={
                **{k: meta.get(k) for k in ("embedding_ms", "vector_search_ms", "rerank_ms", "context_build_ms")},
                "retrieval_ms": meta.get("total_retrieval_ms", 0),
                "llm_ms": 0,
                "total_ms": elapsed,
            },
            session_frame=build_rag_session_frame(library_ids=library_ids, project_id=project_id),
            status="NO_DATA",
        )

    async def rag_answer(
        self,
        *,
        session: Session,
        query: str,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        library_ids: list[str] | None,
        document_ids: list[str] | None = None,
        conversation_history: list[dict],
        llm_provider: LLMProvider,
    ) -> RagAnswerResult:
        started = time.perf_counter()
        scoped_docs: list[uuid.UUID] = []
        if document_ids:
            for raw in document_ids:
                try:
                    scoped_docs.append(uuid.UUID(str(raw)))
                except ValueError:
                    continue
            scoped_docs = list(dict.fromkeys(scoped_docs))

        scoped: list[uuid.UUID] = []
        if scoped_docs:
            scoped = scoped_docs
        else:
            scoped = resolve_library_ids(
                session,
                project_id=project_id,
                requested=library_ids,
                history=conversation_history,
                default_library_ids=self._default_libraries(),
            )
        if not scoped:
            return self._insufficient_result(
                message=(
                    "Pilih perpustakaan knowledge (library) terlebih dahulu, atau konfigurasi "
                    "RAG_DEFAULT_LIBRARY_IDS untuk cakupan proyek."
                ),
                retrieval_payload=None,
                library_ids=[],
                project_id=project_id,
                started=started,
            )

        retrieval = self._retrieval(session)
        try:
            retrieval_payload = retrieval.retrieve(
                query=query,
                workspace_id=workspace_id,
                project_id=project_id,
                library_ids=None if scoped_docs else scoped,
                document_ids=scoped if scoped_docs else None,
            )
        except RetrievalServiceError as exc:
            logger.warning("rag retrieval failed code=%s", exc.code)
            return self._insufficient_result(
                message=f"Knowledge retrieval tidak tersedia ({exc.code}). Coba lagi nanti.",
                retrieval_payload=None,
                library_ids=scoped,
                project_id=project_id,
                started=started,
            )

        evidence = self._evidence_from_payload(retrieval_payload)
        min_score = float(self._settings.rag_min_rerank_score or 0.0)
        if not evidence or (min_score > 0 and self._top_score(evidence) < min_score):
            return self._insufficient_result(
                message=load_rag_insufficient_message(
                    self._settings, session=session, workspace_id=workspace_id, project_id=project_id
                ),
                retrieval_payload=retrieval_payload,
                library_ids=scoped,
                project_id=project_id,
                started=started,
            )

        dialog = bounded_rag_dialog(conversation_history, max_turns=self._settings.rag_conversation_turns)
        system_prompt = load_rag_system_prompt(
            self._settings,
            session=session,
            workspace_id=workspace_id,
            project_id=project_id,
        )
        user_content = build_rag_user_message(question=query, evidence=evidence, dialog=dialog)
        llm_started = time.perf_counter()
        try:
            llm_out = await llm_provider.generate_structured(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                RagLlmOutput,
                temperature=0.2,
                max_tokens=min(self._settings.llm_max_tokens, 2048),
            )
        except Exception as exc:
            logger.warning("rag llm failed %s", type(exc).__name__)
            return self._insufficient_result(
                message="Model jawaban tidak tersedia saat ini. Silakan coba lagi.",
                retrieval_payload=retrieval_payload,
                library_ids=scoped,
                project_id=project_id,
                started=started,
            )
        llm_ms = int((time.perf_counter() - llm_started) * 1000)

        grounding = llm_out.grounding
        valid_ids = validate_cited_ids(llm_out.cited_chunk_ids, evidence)
        citations = citations_from_evidence(evidence, cited_chunk_ids=valid_ids if valid_ids else None)

        if grounding == "INSUFFICIENT_EVIDENCE":
            answer = load_rag_insufficient_message(
                self._settings, session=session, workspace_id=workspace_id, project_id=project_id
            )
            summary = answer
            status = "NO_DATA"
            citations = []
        else:
            status = "SUCCESS"
            if grounding == "PARTIALLY_SUPPORTED" and not llm_out.caveats:
                llm_out.caveats.append("Jawaban hanya sebagian didukung oleh bukti yang tersedia.")
            answer, summary, insights, implications, caveats = normalize_rag_llm_output(llm_out)

        meta = retrieval_payload.get("metadata") or {}
        ctx = retrieval_payload.get("context") or {}
        elapsed = int((time.perf_counter() - started) * 1000)
        rag_insights = [] if grounding == "INSUFFICIENT_EVIDENCE" else insights
        rag_implications = [] if grounding == "INSUFFICIENT_EVIDENCE" else implications
        rag_caveats = list(llm_out.caveats) if grounding == "INSUFFICIENT_EVIDENCE" else caveats
        return RagAnswerResult(
            grounding=grounding,
            answer_text=answer,
            executive_summary=summary,
            insights=rag_insights,
            caveats=rag_caveats,
            business_implications=rag_implications,
            citations=citation_records(citations),
            retrieval_meta={
                "candidate_count": int(ctx.get("total_candidates") or 0),
                "selected_count": int(ctx.get("selected_candidates") or 0),
            },
            execution_metadata={
                **{k: meta.get(k) for k in ("embedding_ms", "vector_search_ms", "rerank_ms", "context_build_ms")},
                "retrieval_ms": meta.get("total_retrieval_ms", 0),
                "llm_ms": llm_ms,
                "total_ms": elapsed,
                "citation_count": len(citations),
                "route": "rag",
                "reranker_model": meta.get("reranker_model"),
                "embedding_model": meta.get("embedding_model"),
            },
            session_frame=build_rag_session_frame(library_ids=scoped, project_id=project_id),
            status=status,
        )

    @staticmethod
    def _evidence_from_payload(payload: dict) -> list[RetrievalCandidate]:
        out: list[RetrievalCandidate] = []
        for row in payload.get("results") or []:
            try:
                out.append(
                    RetrievalCandidate(
                        chunk_id=uuid.UUID(str(row["chunk_id"])),
                        document_id=uuid.UUID(str(row["document_id"])),
                        library_id=uuid.UUID(str(row["library_id"])),
                        workspace_id=uuid.UUID(str(row["workspace_id"])),
                        project_id=uuid.UUID(str(row["project_id"])),
                        text=str(row.get("text") or ""),
                        filename=row.get("filename"),
                        page_number=row.get("page_number"),
                        section=row.get("section"),
                        vector_score=float(row.get("vector_score") or 0.0),
                        rerank_score=row.get("rerank_score"),
                        metadata=dict(row.get("metadata") or {}),
                    )
                )
            except (KeyError, ValueError, TypeError):
                continue
        return out
