#!/usr/bin/env python3
"""M2C shared-collection isolation + latency validation (pilot)."""

from __future__ import annotations

import os
import statistics
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
    collection = os.environ.get("QDRANT_COLLECTION", f"m2c_gate_{uuid.uuid4().hex[:8]}")
    settings = Settings(_env_file=None, qdrant_url=url, qdrant_collection=collection)
    store = QdrantVectorStore(settings)
    embed = MockEmbeddingProvider(dimension=32)
    store.ensure_collection(dimension=embed.dimension)

    ws_a, ws_b = str(uuid.uuid4()), str(uuid.uuid4())
    proj_a, proj_b = str(uuid.uuid4()), str(uuid.uuid4())
    lib_a1, lib_a2, lib_b1 = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())

    corpus: list[tuple[str, str, str, str, str]] = []
    for i in range(8):
        corpus.append((ws_a, proj_a, lib_a1, str(uuid.uuid4()), f"alpha-one chunk {i} sell-in metric"))
    for i in range(8):
        corpus.append((ws_a, proj_a, lib_a2, str(uuid.uuid4()), f"alpha-two chunk {i} promo uplift"))
    for i in range(8):
        corpus.append((ws_b, proj_b, lib_b1, str(uuid.uuid4()), f"beta-one chunk {i} unrelated topic"))

    texts = [row[4] for row in corpus]
    vectors = embed.embed_texts(texts, batch_size=16)
    points: list[VectorPoint] = []
    for (meta, vec) in zip(corpus, vectors, strict=True):
        ws, proj, lib, doc, text = meta
        cid = uuid.uuid4()
        points.append(
            VectorPoint(
                chunk_id=cid,
                vector=vec,
                payload={
                    "workspace_id": ws,
                    "project_id": proj,
                    "library_id": lib,
                    "document_id": doc,
                    "chunk_id": str(cid),
                    "filename": f"{doc}.txt",
                },
            )
        )
    store.upsert(points)
    chunk_count = len(points)

    query_vec = embed.embed_texts(["alpha-one sell-in"], batch_size=1)[0]
    latencies: list[float] = []
    for _ in range(20):
        t0 = time.perf_counter()
        hits = store.search(
            vector=query_vec,
            limit=5,
            filters=VectorSearchFilters(workspace_id=ws_a, project_id=proj_a, library_ids=(lib_a1,)),
        )
        latencies.append((time.perf_counter() - t0) * 1000)

    ok_ws = all(h["payload"]["workspace_id"] == ws_a for h in hits)
    ok_proj = all(h["payload"]["project_id"] == proj_a for h in hits)
    ok_lib = all(h["payload"]["library_id"] == lib_a1 for h in hits)
    no_leak = not any(h["payload"]["workspace_id"] == ws_b for h in hits)

    p50 = statistics.median(latencies)
    p95 = sorted(latencies)[int(len(latencies) * 0.95) - 1]

    recommendation = "KEEP_SHARED_COLLECTION" if ok_ws and ok_proj and ok_lib and no_leak else "REVISIT_COLLECTION_STRATEGY"
    print(
        f"collection={collection} chunks={chunk_count} queries=20 p50_ms={p50:.1f} p95_ms={p95:.1f} "
        f"ws={ok_ws} proj={ok_proj} lib={ok_lib} no_cross_ws={no_leak} recommendation={recommendation}"
    )
    return 0 if recommendation == "KEEP_SHARED_COLLECTION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
