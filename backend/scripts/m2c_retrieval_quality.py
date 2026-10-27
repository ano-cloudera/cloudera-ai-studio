#!/usr/bin/env python3
"""Deterministic Recall@K check over a small mock-indexed corpus (pilot)."""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import Settings
from app.embeddings.provider import MockEmbeddingProvider
from app.vectors.filters import VectorSearchFilters
from app.vectors.store import QdrantVectorStore, VectorPoint

FIXTURE = ROOT / "tests" / "fixtures" / "retrieval_eval.json"


def _recall_at_k(hits: list[dict], must_contain: str) -> bool:
    for hit in hits:
        text = (hit.get("payload") or {}).get("text") or ""
        if must_contain in text:
            return True
    return False


def main() -> int:
    url = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")
    collection = os.environ.get("QDRANT_COLLECTION", f"m2c_quality_{uuid.uuid4().hex[:8]}")
    k = int(os.environ.get("RETRIEVAL_TOP_K", "20"))
    settings = Settings(_env_file=None, qdrant_url=url, qdrant_collection=collection)
    store = QdrantVectorStore(settings)
    embed = MockEmbeddingProvider(dimension=32)
    store.ensure_collection(dimension=embed.dimension)

    ws_a, ws_b = "ws-a", "ws-b"
    proj_a, proj_b = "proj-a", "proj-b"
    lib_a1, lib_a2, lib_b1 = "lib-a1", "lib-a2", "lib-b1"

    corpus: list[tuple[str, str, str, str, str]] = []
    for i in range(6):
        corpus.append((ws_a, proj_a, lib_a1, f"doc-a1-{i}", f"alpha-one sell-in metric narrative chunk {i}"))
    for i in range(6):
        corpus.append((ws_a, proj_a, lib_a2, f"doc-a2-{i}", f"alpha-two promo uplift narrative chunk {i}"))
    for i in range(6):
        corpus.append((ws_b, proj_b, lib_b1, f"doc-b1-{i}", f"beta-one unrelated topic chunk {i}"))

    texts = [row[4] for row in corpus]
    vectors = embed.embed_texts(texts, batch_size=32)
    points: list[VectorPoint] = []
    for meta, vec in zip(corpus, vectors, strict=True):
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
                    "text": text,
                    "filename": f"{doc}.txt",
                },
            )
        )
    store.upsert(points)

    cases = json.loads(FIXTURE.read_text())
    hits = 0
    for case in cases:
        ws = ws_a if case["workspace_key"] == "A" else ws_b
        proj = proj_a if case["project_key"] == "A" else proj_b
        lib = {"A1": lib_a1, "A2": lib_a2, "B1": lib_b1}[case["library_key"]]
        qvec = embed.embed_texts([case["query"]], batch_size=1)[0]
        results = store.search(
            vector=qvec,
            limit=k,
            filters=VectorSearchFilters(workspace_id=ws, project_id=proj, library_ids=(lib,)),
        )
        if _recall_at_k(results, case["must_contain"]):
            hits += 1

    recall = hits / len(cases) if cases else 0.0
    print(f"collection={collection} cases={len(cases)} recall@{k}={recall:.2f} ({hits}/{len(cases)})")
    return 0 if recall >= 0.8 else 1


if __name__ == "__main__":
    raise SystemExit(main())
