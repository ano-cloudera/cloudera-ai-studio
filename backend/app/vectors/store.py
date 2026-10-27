from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.core.config import Settings
from app.vectors.filters import VectorSearchFilters, build_qdrant_filter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VectorPoint:
    chunk_id: uuid.UUID
    vector: list[float]
    payload: dict[str, Any]


@runtime_checkable
class VectorStore(Protocol):
    def ensure_collection(self, *, dimension: int) -> None: ...

    def upsert(self, points: list[VectorPoint]) -> None: ...

    def delete_document(self, *, document_id: uuid.UUID) -> None: ...

    def search(
        self,
        *,
        vector: list[float],
        limit: int,
        filters: VectorSearchFilters | None = None,
    ) -> list[dict]: ...

    def collection_vector_size(self) -> int | None: ...

    def health(self) -> dict: ...


class QdrantVectorStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = None

    @property
    def collection(self) -> str:
        return self._settings.qdrant_collection

    def _client_instance(self):
        if self._client is None:
            from qdrant_client import QdrantClient

            url = (self._settings.qdrant_url or "").strip()
            if not url:
                raise RuntimeError("QDRANT_URL not configured")
            api_key = self._settings.qdrant_api_key.get_secret_value() or None
            self._client = QdrantClient(
                url=url,
                api_key=api_key,
                timeout=float(self._settings.qdrant_timeout_seconds),
            )
        return self._client

    def ensure_collection(self, *, dimension: int) -> None:
        from qdrant_client.http import models as qmodels

        client = self._client_instance()
        name = self.collection
        exists = client.collection_exists(name)
        if not exists:
            client.create_collection(
                collection_name=name,
                vectors_config=qmodels.VectorParams(size=dimension, distance=qmodels.Distance.COSINE),
            )
            logger.info("qdrant collection created name=%s dim=%s", name, dimension)

    def upsert(self, points: list[VectorPoint]) -> None:
        from qdrant_client.http import models as qmodels

        if not points:
            return
        client = self._client_instance()
        client.upsert(
            collection_name=self.collection,
            points=[
                qmodels.PointStruct(id=str(p.chunk_id), vector=p.vector, payload=p.payload) for p in points
            ],
        )

    def delete_document(self, *, document_id: uuid.UUID) -> None:
        from qdrant_client.http import models as qmodels

        client = self._client_instance()
        if not client.collection_exists(self.collection):
            return
        try:
            client.delete(
                collection_name=self.collection,
                points_selector=qmodels.FilterSelector(
                    filter=qmodels.Filter(
                        must=[
                            qmodels.FieldCondition(
                                key="document_id",
                                match=qmodels.MatchValue(value=str(document_id)),
                            )
                        ]
                    )
                ),
            )
        except Exception as exc:
            # Idempotent cleanup — no points yet is OK during first ingest / reprocess.
            logger.warning("qdrant delete_document noop document_id=%s (%s)", document_id, type(exc).__name__)

    def collection_vector_size(self) -> int | None:
        client = self._client_instance()
        if not client.collection_exists(self.collection):
            return None
        info = client.get_collection(self.collection)
        params = info.config.params.vectors
        if hasattr(params, "size"):
            return int(params.size)
        return None

    def search(
        self,
        *,
        vector: list[float],
        limit: int,
        filters: VectorSearchFilters | None = None,
    ) -> list[dict]:
        client = self._client_instance()
        qfilter = build_qdrant_filter(filters) if filters else None
        hits = client.search(collection_name=self.collection, query_vector=vector, limit=limit, query_filter=qfilter)
        return [{"id": str(hit.id), "score": hit.score, "payload": hit.payload or {}} for hit in hits]

    def health(self) -> dict:
        try:
            client = self._client_instance()
            collections = client.get_collections()
            names = [c.name for c in collections.collections]
            return {
                "status": "ready" if self.collection in names else "collection_missing",
                "url_configured": bool((self._settings.qdrant_url or "").strip()),
                "collection": self.collection,
            }
        except Exception as exc:
            return {"status": "not_ready", "error": type(exc).__name__}


def build_vector_store(settings: Settings) -> VectorStore | None:
    if not (settings.qdrant_url or "").strip():
        return None
    return QdrantVectorStore(settings)
