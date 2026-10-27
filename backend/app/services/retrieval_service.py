from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.platform_models import DocumentChunkRow, DocumentRow
from app.embeddings.provider import EmbeddingProvider, get_embedding_provider
from app.rerank.provider import Reranker, get_reranker
from app.retrieval.context_builder import ContextBuilder
from app.retrieval.types import RetrievalCandidate
from app.vectors.filters import VectorSearchFilters
from app.vectors.store import VectorStore, build_vector_store

logger = logging.getLogger(__name__)


class RetrievalServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class RetrievalService:
    def __init__(
        self,
        settings: Settings,
        session: Session,
        *,
        embedding: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        self._settings = settings
        self._session = session
        self._embedding = embedding or get_embedding_provider(settings)
        self._vectors = vector_store if vector_store is not None else build_vector_store(settings)
        self._reranker = reranker or get_reranker(settings)
        self._context_builder = ContextBuilder(max_context_tokens=settings.rag_max_context_tokens)

    def _validate_vector_backend(self) -> None:
        if not self._vectors:
            raise RetrievalServiceError("qdrant_unavailable", "Vector store is not configured", 503)

    def _validate_dimension(self) -> None:
        try:
            col_dim = self._vectors.collection_vector_size()  # type: ignore[union-attr]
        except Exception as exc:
            raise RetrievalServiceError(
                "qdrant_unavailable",
                "Vector store is not reachable",
                503,
            ) from exc
        if col_dim is None:
            return
        if col_dim != self._embedding.dimension:
            raise RetrievalServiceError(
                "dimension_mismatch",
                "Embedding dimension does not match indexed collection configuration",
                409,
            )

    def retrieve(
        self,
        *,
        query: str,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        library_ids: list[uuid.UUID] | None = None,
        document_ids: list[uuid.UUID] | None = None,
        top_k: int | None = None,
    ) -> dict:
        q = (query or "").strip()
        if not q:
            raise RetrievalServiceError("invalid_query", "Query is required", 422)

        self._validate_vector_backend()
        self._validate_dimension()

        k = top_k or self._settings.retrieval_top_k
        timings: dict[str, int] = {}
        started = time.perf_counter()

        t0 = time.perf_counter()
        try:
            query_vector = self._embedding.embed_texts([q], batch_size=1)[0]
        except Exception as exc:
            raise RetrievalServiceError("embedding_unavailable", "Query embedding failed", 503) from exc
        timings["embedding_ms"] = int((time.perf_counter() - t0) * 1000)

        filters = VectorSearchFilters(
            workspace_id=str(workspace_id),
            project_id=str(project_id),
            library_ids=tuple(str(i) for i in library_ids) if library_ids else None,
            document_ids=tuple(str(i) for i in document_ids) if document_ids else None,
        )

        t1 = time.perf_counter()
        try:
            hits = self._vectors.search(vector=query_vector, limit=k, filters=filters)  # type: ignore[union-attr]
        except Exception as exc:
            raise RetrievalServiceError("qdrant_unavailable", "Vector search failed", 503) from exc
        timings["vector_search_ms"] = int((time.perf_counter() - t1) * 1000)

        candidates = self._hydrate_candidates(hits, workspace_id=workspace_id, project_id=project_id)
        if not candidates:
            timings["total_retrieval_ms"] = int((time.perf_counter() - started) * 1000)
            ctx = self._context_builder.build(q, [], total_candidates=0)
            return self._package(q, ctx, timings, rerank_fallback=False)

        t2 = time.perf_counter()
        try:
            ranked = self._reranker.rerank(q, candidates, top_n=self._settings.rerank_top_n)
        except Exception as exc:
            logger.warning("reranker failed (%s) — falling back to vector order", type(exc).__name__)
            from app.rerank.provider import NoOpReranker

            ranked = NoOpReranker().rerank(q, candidates, top_n=self._settings.rerank_top_n)
            rerank_fallback = True
        else:
            rerank_fallback = any((c.metadata or {}).get("rerank_fallback") for c in ranked)
        timings["rerank_ms"] = int((time.perf_counter() - t2) * 1000)

        t3 = time.perf_counter()
        ctx = self._context_builder.build(q, ranked, total_candidates=len(candidates))
        timings["context_build_ms"] = int((time.perf_counter() - t3) * 1000)
        timings["total_retrieval_ms"] = int((time.perf_counter() - started) * 1000)

        return self._package(q, ctx, timings, rerank_fallback=rerank_fallback)

    def _hydrate_candidates(
        self,
        hits: list[dict],
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> list[RetrievalCandidate]:
        if not hits:
            return []
        chunk_ids = [uuid.UUID(str(hit["id"])) for hit in hits]
        rows = self._session.execute(
            select(DocumentChunkRow).where(DocumentChunkRow.id.in_(chunk_ids))
        ).scalars().all()
        by_id = {row.id: row for row in rows}
        doc_ids = {row.document_id for row in rows}
        docs = {
            d.id: d
            for d in self._session.execute(select(DocumentRow).where(DocumentRow.id.in_(doc_ids))).scalars().all()
        }

        out: list[RetrievalCandidate] = []
        for hit in hits:
            cid = uuid.UUID(str(hit["id"]))
            row = by_id.get(cid)
            if not row:
                continue
            if row.workspace_id != workspace_id or row.project_id != project_id:
                logger.warning("retrieval isolation drop chunk_id=%s", cid)
                continue
            payload = hit.get("payload") or {}
            doc = docs.get(row.document_id)
            filename = doc.original_filename if doc else payload.get("filename")
            out.append(
                RetrievalCandidate(
                    chunk_id=row.id,
                    document_id=row.document_id,
                    library_id=row.library_id,
                    workspace_id=row.workspace_id,
                    project_id=row.project_id,
                    text=row.text,
                    filename=filename,
                    page_number=row.page_number,
                    section=row.section,
                    vector_score=float(hit.get("score") or 0.0),
                    metadata=dict(row.metadata_json or {}),
                )
            )
        return out

    def _package(self, query: str, ctx, timings: dict, *, rerank_fallback: bool) -> dict:
        def _cand(c: RetrievalCandidate) -> dict:
            return {
                "chunk_id": str(c.chunk_id),
                "document_id": str(c.document_id),
                "library_id": str(c.library_id),
                "workspace_id": str(c.workspace_id),
                "project_id": str(c.project_id),
                "text": c.text,
                "filename": c.filename,
                "page_number": c.page_number,
                "section": c.section,
                "vector_score": c.vector_score,
                "rerank_score": c.rerank_score,
                "metadata": c.metadata,
            }

        def _cite(c) -> dict:
            d = asdict(c)
            d["document_id"] = str(c.document_id)
            d["chunk_id"] = str(c.chunk_id)
            return d

        return {
            "query": query,
            "results": [_cand(c) for c in ctx.evidence],
            "citations": [_cite(c) for c in ctx.citations],
            "context": {
                "total_candidates": ctx.total_candidates,
                "selected_candidates": ctx.selected_candidates,
                "token_budget_used": ctx.token_budget_used,
            },
            "metadata": {
                "embedding_model": self._embedding.model_name,
                "embedding_dimension": self._embedding.dimension,
                "reranker_model": self._reranker.model_name,
                "rerank_fallback": rerank_fallback,
                **timings,
            },
        }
