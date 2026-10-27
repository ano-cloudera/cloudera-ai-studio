from __future__ import annotations

import hashlib
import logging
import math
from functools import lru_cache
from typing import Protocol, runtime_checkable

from app.core.config import Settings

logger = logging.getLogger(__name__)


@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def model_name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed_texts(self, texts: list[str], *, batch_size: int) -> list[list[float]]: ...

    def health(self) -> dict: ...


class MockEmbeddingProvider:
    """Deterministic low-dim vectors for unit/integration tests without GPU."""

    def __init__(self, *, model_name: str = "mock-hash", dimension: int = 64) -> None:
        self._model_name = model_name
        self._dimension = dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_texts(self, texts: list[str], *, batch_size: int) -> list[list[float]]:
        _ = batch_size
        out: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vec = []
            for i in range(self._dimension):
                vec.append((digest[i % len(digest)] / 255.0) * 2 - 1)
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out

    def health(self) -> dict:
        return {"status": "ready", "provider": "mock"}


class BgeM3EmbeddingProvider:
    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = _load_sentence_transformer(model_name)
        dim = int(self._model.get_sentence_embedding_dimension())
        self._dimension = dim

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_texts(self, texts: list[str], *, batch_size: int) -> list[list[float]]:
        vectors = self._model.encode(
            texts,
            batch_size=max(1, batch_size),
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [vec.tolist() for vec in vectors]

    def health(self) -> dict:
        return {"status": "ready", "provider": "bge_m3", "model": self._model_name, "dimension": self._dimension}


@lru_cache(maxsize=2)
def _load_sentence_transformer(model_name: str):
    from sentence_transformers import SentenceTransformer

    logger.info("loading embedding model %s", model_name)
    return SentenceTransformer(model_name)


@lru_cache(maxsize=4)
def _cached_embedding_provider(provider_key: str, model_name: str) -> EmbeddingProvider:
    if provider_key in {"mock", "hash", "test"}:
        return MockEmbeddingProvider(model_name=model_name or "mock-hash")
    if provider_key in {"bge_m3", "bge-m3", "sentence_transformers"}:
        return BgeM3EmbeddingProvider(model_name)
    raise RuntimeError(f"unsupported EMBEDDING_PROVIDER: {provider_key}")


def get_embedding_provider(settings: Settings) -> EmbeddingProvider:
    return _cached_embedding_provider(
        settings.embedding_provider.strip().lower(),
        (settings.embedding_model or "").strip(),
    )
