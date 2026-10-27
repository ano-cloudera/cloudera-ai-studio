#!/usr/bin/env python3
"""Lightweight shared-collection + metadata filter validation (M2 gate)."""

from __future__ import annotations

import os
import sys
import time
import uuid

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import Settings
from app.embeddings.provider import MockEmbeddingProvider
from app.vectors.filters import VectorSearchFilters
from app.vectors.store import QdrantVectorStore, VectorPoint


def main() -> int:
    url = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")
    collection = os.environ.get("QDRANT_COLLECTION", f"gate_{uuid.uuid4().hex[:8]}")
    settings = Settings(_env_file=None, qdrant_url=url, qdrant_collection=collection)
    store = QdrantVectorStore(settings)
    embed = MockEmbeddingProvider(dimension=32)
    store.ensure_collection(dimension=embed.dimension)

    ws_a, ws_b = str(uuid.uuid4()), str(uuid.uuid4())
    proj = str(uuid.uuid4())
    lib = str(uuid.uuid4())
    doc_a, doc_b = str(uuid.uuid4()), str(uuid.uuid4())

    texts = [f"docA chunk {i}" for i in range(5)] + [f"docB chunk {i}" for i in range(5)]
    vectors = embed.embed_texts(texts, batch_size=8)
    points: list[VectorPoint] = []
    for i, (text, vec) in enumerate(zip(texts, vectors, strict=True)):
        cid = uuid.uuid4()
        doc_id = doc_a if i < 5 else doc_b
        points.append(
            VectorPoint(
                chunk_id=cid,
                vector=vec,
                payload={
                    "workspace_id": ws_a if i < 5 else ws_b,
                    "project_id": proj,
                    "library_id": lib,
                    "document_id": doc_id,
                    "chunk_id": str(cid),
                    "filename": f"{doc_id}.txt",
                },
            )
        )
    started = time.perf_counter()
    store.upsert(points)
    upsert_ms = int((time.perf_counter() - started) * 1000)

    query = vectors[0]
    started = time.perf_counter()
    hits = store.search(
        vector=query,
        limit=5,
        filters=VectorSearchFilters(workspace_id=ws_a, project_id=proj, document_ids=(doc_a,)),
    )
    search_ms = int((time.perf_counter() - started) * 1000)

    isolated = all(h["payload"].get("document_id") == doc_a for h in hits)
    print(f"collection={collection} upsert_ms={upsert_ms} search_ms={search_ms} hits={len(hits)} isolated={isolated}")
    if not isolated:
        return 1
    store.delete_document(document_id=uuid.UUID(doc_a))
    after = store.search(
        vector=query,
        limit=5,
        filters=VectorSearchFilters(workspace_id=ws_a, project_id=proj, document_ids=(doc_a,)),
    )
    print(f"after_delete_hits={len(after)}")
    return 0 if len(after) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
