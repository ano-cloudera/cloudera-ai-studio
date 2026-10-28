# CAI deployment environment contract

**Related audit:** [CAI_3_APP_PERSISTENCE_ARCHITECTURE_AUDIT.md](./CAI_3_APP_PERSISTENCE_ARCHITECTURE_AUDIT.md)

This document maps **existing** configuration names traced from `backend/app/core/config.py`, `frontend/next.config.mjs`, and `config/examples/accelerator.env.example`. Proposed unified `CAI_DATA_DIR` is **future** (CONFIG-001) — not implemented in this milestone.

---

## Backend CAI application

| Variable | Purpose | Required? | CAI target value | Secret? | Persistent? |
|----------|---------|-------------|------------------|---------|-------------|
| `STATE_STORE` | Legacy label; when `DATABASE_URL` is set, conversation/usage use platform DB | Use `sqlite` or `postgres` with URL | Either | No | N/A |
| `CAI_DATA_DIR` | Optional local persistence root | Local sim | e.g. `runtime/cai-sim` | No | **Yes** |
| `DATABASE_URL` / `POSTGRES_URL` | Platform metadata DSN (**PostgreSQL or SQLite**) | **Yes** (full product) | `postgresql+psycopg://…` or `sqlite+pysqlite:///…/studio.db` | Often yes (Postgres password) | DB file or external volume |
| `UVICORN_WORKERS` | Backend worker count | **Must be `1` for SQLite metadata** | `1` | No | No |
| `DOCUMENT_STORAGE_ROOT` | Knowledge + attachment blob root | Yes | Path on NFS mount (e.g. `${CAI_DATA_DIR}/documents`) | No | **Yes** |
| `SEMANTIC_RUNTIME_STORAGE_ROOT` | Published OSSIE / deployment artifacts | Yes | NFS path (e.g. `${CAI_DATA_DIR}/semantic-runtime`) | No | **Yes** |
| `QDRANT_URL` | Vector service HTTP endpoint | Yes for RAG/Knowledge vectors | URL of Qdrant CAI app service | No | N/A |
| `QDRANT_COLLECTION` | Collection name | Yes when Qdrant used | String (default `accelerator_chunks`) | No | N/A |
| `QDRANT_API_KEY` | Qdrant auth | If Qdrant secured | CAI secret | **Yes** | No |
| `QDRANT_TIMEOUT_SECONDS` | Client timeout | No | Integer | No | No |
| `CORS_ORIGINS` | Allowed browser origins | Yes when FE separate | Frontend public URL(s), comma-separated | No | No |
| `FEATURE_PROFILE` | RAG vs Ask Data gating | Recommended | e.g. `FULL_ACCELERATOR` | No | No |
| `DEPLOYMENT_PROFILE` | Readiness labeling | No | `local` / deployment name | No | No |
| `DEFAULT_PROJECT_SLUG` | Seed project selection | Recommended | Slug matching bootstrap | No | No |
| `DOCUMENT_PDF_USE_PYPDF` | PDF text extraction backend | No | `true`/`false` | No | No |
| `DOCUMENT_AUTO_PROCESS` | Auto-ingest on upload | No | `true`/`false` | No | No |
| `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` | RAG embeddings | For RAG | Provider config | No | No |
| `RERANKER_PROVIDER` / `RERANKER_MODEL` | RAG rerank | Optional | Provider config | No | No |
| `CHAT_ATTACHMENT_TTL_DAYS` | Temp attachment retention | No | Integer (default 7) | No | N/A |
| `DATA_BACKEND` | Legacy Ask Data engine | Optional | `duckdb` / `impala` / etc. | No | N/A |
| `DUCKDB_PATH` | Ask Data analytical file | If `DATA_BACKEND=duckdb` | NFS path optional | No | **Yes** (if used) |
| `GEMINI_API_KEY` / `OPENAI_API_KEY` / `QWEN_API_TOKEN` | LLM providers | At least one for chat | CAI secrets | **Yes** | No |
| `GEMINI_MODEL` / etc. | Model IDs | No | String | No | No |
| `USAGE_DB_PATH` | Usage sqlite file | Only if `STATE_STORE=sqlite` without PG usage | File path | No | Yes |
| `conversation_db_path` | Legacy conv sqlite | Implicit default under runtime | File path | No | Yes |
| `CONNECTOR_METADATA_CACHE_TTL_SECONDS` | In-memory cache TTL | No | Seconds | No | No |
| `RAG_SYSTEM_PROMPT_PATH` | Default RAG prompt file | No | Path in image or NFS | No | Optional |
| `BRAVE_API_KEY` | MCP Brave Search stdio preset (`@modelcontextprotocol/server-brave-search`) | Optional | CAI Backend secret | **Yes** | No |
| `MCP_CONNECTORS_JSON` | Legacy MCP connector list when workspace has no servers | Optional | JSON array | No | No |

Workspace MCP server entries (stdio command, SSE URL, **env var names only**) are stored in platform metadata via `PUT /api/v1/mcp/settings` — never secret values in JSON.

### Connector / AI registry secrets (stored in DB as references)

| Pattern | Purpose | Required? | CAI target | Secret? | Persistent? |
|---------|---------|-------------|------------|---------|-------------|
| `env://VAR_NAME` in `secret_ref` columns | Resolve connector/provider credentials | Per connector/provider | `VAR_NAME` set in Backend CAI secrets | Ref in DB; value in env | Ref **yes** |

Implementations: `backend/app/ai_registry/secrets.py`, connector create/update APIs.

---

## Frontend CAI application

| Variable | Purpose | Required? | CAI target value | Secret? | Persistent? |
|----------|---------|-------------|------------------|---------|-------------|
| `BACKEND_API_URL` | Next.js rewrite proxy target (server-side) | **Yes** in split deploy | `http(s)://<backend-service>:8001` | No | No |
| `NEXT_PUBLIC_BACKEND_URL` | Client-visible API base (if used by client fetches) | Recommended | Same public URL as users reach backend | No | No |
| `NEXT_PUBLIC_APP_NAME` | UI title | No | String | No | No |
| `NEXT_PUBLIC_FEATURE_*` | Feature flags | No | `true`/`false` | No | No |

Source: `frontend/next.config.mjs` (`BACKEND_API_URL` || default `http://127.0.0.1:8001`).

---

## Qdrant CAI application

| Variable | Purpose | Required? | Notes |
|----------|---------|-------------|-------|
| Qdrant `storage` path | Vector + payload durability | **Yes** | Configure in Qdrant deployment (not in Cloudera AI Studio repo) |
| Service URL | Reachable from Backend | **Yes** | Becomes Backend `QDRANT_URL` |
| `QDRANT_API_KEY` | Auth | Optional | Must match Backend env if enabled |

---

## External data sources (not application metadata)

| Variable / config | Purpose |
|-------------------|---------|
| Connector rows in Postgres (`connectors.config`, `secret_ref`) | Banking PostgreSQL, Impala, Trino, etc. |
| Legacy `IMPALA_*` / profile blocks in `.env` | Optional Impala Ask Data |
| `TRINO_*` in settings | Optional Trino |

**Never** point `DATABASE_URL` at customer business databases.

---

## Proposed future variable (not implemented)

| Variable | Purpose |
|----------|---------|
| `CAI_DATA_DIR` | Single mount root deriving `DOCUMENT_STORAGE_ROOT`, `SEMANTIC_RUNTIME_STORAGE_ROOT`, and future `DATABASE_URL=sqlite:///${CAI_DATA_DIR}/metadata/app.db` |

---

## Minimal CAI split examples

### Backend

```bash
STATE_STORE=postgres
DATABASE_URL=postgresql+psycopg://user:pass@postgres-host:5432/accelerator
DOCUMENT_STORAGE_ROOT=/home/cdsw/cai-studio-data/documents
SEMANTIC_RUNTIME_STORAGE_ROOT=/home/cdsw/cai-studio-data/var/semantic-runtime
QDRANT_URL=http://qdrant-service:6333
CORS_ORIGINS=https://cai-frontend.example.com
```

### Frontend

```bash
BACKEND_API_URL=http://backend-service:8001
NEXT_PUBLIC_BACKEND_URL=https://cai-backend.example.com
```

### Qdrant

Persistent volume mounted at Qdrant data directory; expose port 6333 (or TLS terminator) to Backend only.

---

## Deployment checklist

1. Postgres metadata reachable from Backend; migrations applied (`DATABASE_URL` set).  
2. NFS (or equivalent) mounted for document + semantic roots before Backend ready check passes.  
3. Qdrant running with persistent storage; `QDRANT_URL` set on Backend.  
4. Frontend `BACKEND_API_URL` points to Backend service; CORS includes frontend origin.  
5. LLM and connector secrets in CAI secret store; DB holds `env://` refs only.
