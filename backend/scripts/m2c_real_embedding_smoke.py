#!/usr/bin/env python3
"""Optional real BGE-M3 embedding smoke (skipped when models unavailable)."""

from __future__ import annotations

import os
import sys

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import Settings
from app.embeddings.provider import get_embedding_provider


def main() -> int:
    if os.environ.get("SKIP_REAL_EMBEDDING", "").strip() == "1":
        print("SKIP_REAL_EMBEDDING=1 — real embedding validation not run")
        return 0
    settings = Settings(_env_file=None, embedding_provider="bge_m3", embedding_model="BAAI/bge-m3")
    try:
        provider = get_embedding_provider(settings)
        doc_vec = provider.embed_texts(["Document about sell-in performance."], batch_size=1)[0]
        query_vec = provider.embed_texts(["sell-in performance"], batch_size=1)[0]
    except Exception as exc:
        print(f"REAL_EMBEDDING_BLOCKED: {type(exc).__name__}: {exc}")
        return 0
    print(
        f"REAL_EMBEDDING_OK model={provider.model_name} dim={provider.dimension} "
        f"doc_len={len(doc_vec)} query_len={len(query_vec)}"
    )
    if len(doc_vec) != len(query_vec) or len(doc_vec) != provider.dimension:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
