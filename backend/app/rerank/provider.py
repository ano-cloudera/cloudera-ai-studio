from __future__ import annotations

import logging
from functools import lru_cache
from typing import Protocol, runtime_checkable

from app.core.config import Settings
from app.retrieval.types import RetrievalCandidate

logger = logging.getLogger(__name__)


@runtime_checkable
class Reranker(Protocol):
    @property
    def model_name(self) -> str: ...

    def rerank(self, query: str, candidates: list[RetrievalCandidate], *, top_n: int) -> list[RetrievalCandidate]: ...

    def health(self) -> dict: ...


class NoOpReranker:
    @property
    def model_name(self) -> str:
        return "none"

    def rerank(self, query: str, candidates: list[RetrievalCandidate], *, top_n: int) -> list[RetrievalCandidate]:
        _ = query
        ordered = sorted(candidates, key=lambda c: c.vector_score, reverse=True)
        out: list[RetrievalCandidate] = []
        for cand in ordered[:top_n]:
            out.append(
                RetrievalCandidate(
                    chunk_id=cand.chunk_id,
                    document_id=cand.document_id,
                    library_id=cand.library_id,
                    workspace_id=cand.workspace_id,
                    project_id=cand.project_id,
                    text=cand.text,
                    filename=cand.filename,
                    page_number=cand.page_number,
                    section=cand.section,
                    vector_score=cand.vector_score,
                    rerank_score=cand.vector_score,
                    metadata={**cand.metadata, "rerank_fallback": True},
                )
            )
        return out

    def health(self) -> dict:
        return {"status": "ready", "provider": "none"}


class BgeReranker:
    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = _load_cross_encoder(model_name)

    @property
    def model_name(self) -> str:
        return self._model_name

    def rerank(self, query: str, candidates: list[RetrievalCandidate], *, top_n: int) -> list[RetrievalCandidate]:
        if not candidates:
            return []
        pairs = [(query, c.text) for c in candidates]
        scores = self._model.predict(pairs)
        ranked = sorted(zip(candidates, scores, strict=True), key=lambda row: float(row[1]), reverse=True)
        out: list[RetrievalCandidate] = []
        for cand, score in ranked[:top_n]:
            out.append(
                RetrievalCandidate(
                    chunk_id=cand.chunk_id,
                    document_id=cand.document_id,
                    library_id=cand.library_id,
                    workspace_id=cand.workspace_id,
                    project_id=cand.project_id,
                    text=cand.text,
                    filename=cand.filename,
                    page_number=cand.page_number,
                    section=cand.section,
                    vector_score=cand.vector_score,
                    rerank_score=float(score),
                    metadata=cand.metadata,
                )
            )
        return out

    def health(self) -> dict:
        return {"status": "ready", "provider": "bge", "model": self._model_name}


@lru_cache(maxsize=2)
def _load_cross_encoder(model_name: str):
    from sentence_transformers import CrossEncoder

    logger.info("loading reranker model %s", model_name)
    return CrossEncoder(model_name)


@lru_cache(maxsize=4)
def _cached_reranker(provider_key: str, model_name: str) -> Reranker:
    if provider_key in {"none", "off", "mock"}:
        return NoOpReranker()
    if provider_key in {"bge", "bge_m3", "cross_encoder"}:
        return BgeReranker(model_name)
    raise RuntimeError(f"unsupported RERANKER_PROVIDER: {provider_key}")


def get_reranker(settings: Settings) -> Reranker:
    return _cached_reranker(
        settings.reranker_provider.strip().lower(),
        (settings.reranker_model or "").strip(),
    )
