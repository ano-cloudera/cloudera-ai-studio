# RAG / Document Intelligence — Design

**Status:** M2A–M2D implemented (through grounded RAG chat). Hybrid Ask Data + RAG router is **not** implemented.

## Ingestion pipeline (M2B)

```text
Upload (HTTP multipart)
  → Document Registry (Postgres: status=QUEUED → PROCESSING → READY|FAILED)
  → Parser (Docling preferred; fallbacks)
  → Chunker
  → Embedder (mock dev default; BAAI/bge-m3 production path)
  → Qdrant upsert (vector + payload)
  → document_chunks rows (source of truth for text + provenance)
```

## Retrieval pipeline (M2C)

```text
User query
  → Query embedding (same EmbeddingProvider as ingest)
  → Dimension check vs Qdrant collection
  → VectorStore.search(limit=RETRIEVAL_TOP_K, VectorSearchFilters)
  → Hydrate chunks from Postgres (drop cross workspace/project rows)
  → Reranker (BAAI/bge-reranker-v2-m3 or RERANKER_PROVIDER=none)
  → ContextBuilder (RAG_MAX_CONTEXT_TOKENS budget)
  → Citations[] + evidence[] (normalized RetrievalCandidate)
```

Orchestration lives in `RetrievalService` — not in FastAPI handlers.

### Configuration

| Setting | Default | Purpose |
|---------|---------|---------|
| `RETRIEVAL_TOP_K` | 20 | Qdrant candidate pool |
| `RERANK_TOP_N` | 5 | Evidence passed to context builder |
| `RAG_MAX_CONTEXT_TOKENS` | 4096 | Token budget (≈ chars/4 estimate) |
| `RERANKER_PROVIDER` | `none` | `bge` for CrossEncoder rerank |
| `RERANKER_MODEL` | `BAAI/bge-reranker-v2-m3` | |
| `EMBEDDING_PROVIDER` | `mock` | Must match index for search (`409` on mismatch) |

### API (M2C)

`POST /api/v1/retrieval/search` — validation/debug; **not** wired to `/chat`.

Request: `{ query, project_id?, library_ids?, document_ids?, top_k? }`

Response: `results`, `citations`, `context`, `metadata` (models, timings, `rerank_fallback`).

## NFS layout (pilot)

See M2A doc — Postgres + object store hold binaries; chunk text in Postgres.

## Citation representation

Grounded from retrieved `RetrievalCandidate` only — no fabricated page/section:

```json
{
  "document_id": "uuid",
  "filename": "policy-q4.pdf",
  "page_number": 12,
  "section": null,
  "chunk_id": "uuid",
  "source_uri": null,
  "snippet": "…",
  "score": 0.87
}
```

Scores prefer `rerank_score` when present; otherwise `vector_score`.

## Qdrant payload (minimum)

- `workspace_id`, `project_id`, `library_id`, `document_id`, `chunk_id`
- `filename` (and optional snippet fields from ingest)

Full chunk text for answers is loaded from **`document_chunks`** after search.

## Qdrant collection strategy

**Pilot decision (M2C gate):** **shared collection + mandatory metadata filtering** on every query.

| Criterion | M2C pilot result |
|-----------|------------------|
| Isolation | workspace / project / library filters enforced; PG hydration drops mismatches |
| Latency | 24 chunks, 20 queries: p50 ~1.6 ms, p95 ~1.8 ms (local Qdrant) |
| Recall | Mock corpus eval: Recall@20 = 1.00 (12/12 deterministic set) |
| Recommendation | **KEEP_SHARED_COLLECTION** |

Revisit per-library/per-workspace collections if production chunk volume or filter overhead fails SLO.

## RAG answer pipeline (M2D)

```text
Chat (mode=rag) or POST /api/v1/rag/query
  → RAGService.rag_answer
  → RetrievalService (scoped library_ids)
  → RAG system prompt + evidence blocks
  → ProviderRegistry LLM (structured RagLlmOutput)
  → Grounding gate (SUPPORTED / PARTIALLY_SUPPORTED / INSUFFICIENT_EVIDENCE)
  → Citations (deduped, chunk-grounded)
  → AskDataResponse (strategy=rag, route=rag)
```

**Library scope:** request `library_ids`, else session `rag_library_ids`, else `RAG_DEFAULT_LIBRARY_IDS`. Never searches all workspace libraries by default.

**Insufficient evidence:** no hits, missing library scope, or LLM `INSUFFICIENT_EVIDENCE` → `NO_DATA` + safe message (no domain hallucination).

**Chat:** same SSE contract; progress labels: Understanding question → Searching knowledge → Reviewing sources → Preparing answer.

**Follow-up:** bounded prior turns (`RAG_CONVERSATION_TURNS`); scope persisted in `session_frame`.

Optional future: query rewrite, hybrid SQL + RAG router — out of M2D scope.

## Testing

- Unit: filters, context budget, citations, noop rerank
- Integration: upload → ingest → `POST /api/v1/retrieval/search` (Postgres + Qdrant)
- Scripts: `m2c_isolation_validation.py`, `m2c_retrieval_quality.py`, `m2c_real_embedding_smoke.py`
