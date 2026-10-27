# API Contract — Target & Current

## Versioning strategy

- **Current (stable):** unprefixed routes used by `frontend` — **must remain through M1 and beyond** for chat/models/usage:
  - `POST /chat`, `POST /chat/stream`
  - `GET /models`
  - `GET /usage/summary`, `GET /usage/events`, `GET /usage/export.csv`
- **Target:** new resources under `/api/v1/...` for workspace, project, documents, connectors, prompts, skills, etc.

### M1 routing rule

`/api/v1` handlers **reuse existing services** — e.g. `ChatService.run` / `ChatService.stream`, `ProviderRegistry`, `UsageStore`. They are thin HTTP adapters + auth/context injection, **not** duplicate chat engines or LangGraph graphs.

## Current endpoints (backend)

| Method | Path | Request | Response |
|--------|------|---------|----------|
| GET | `/health` | — | `{ "status": "ok" }` |
| GET | `/health/ready` | — | `{ "status": "ready"|"not_ready", "components": {...} }` |
| GET | `/models` | — | `{ "models": ModelInfo[] }` |
| GET | `/random-queries` | `domain?`, `difficulty?`, `limit?` | Question bank slice |
| POST | `/chat` | `AskDataRequest` | `AskDataResponse` |
| POST | `/chat/stream` | `AskDataRequest` | SSE (see below) |
| DELETE | `/chat/sessions/{session_id}` | — | `{ "deleted": n }` |
| GET | `/usage/summary` | `days?`, `mtd?` | `UsageSummary` |
| GET | `/usage/events` | `days?`, `limit?` | events list |
| GET | `/usage/export.csv` | query params | CSV stream |

### M1 platform endpoints (`STATE_STORE=postgres` + `DATABASE_URL`)

| Method | Path | Response |
|--------|------|----------|
| GET | `/api/v1/workspaces` | `{ "workspaces": [...] }` |
| GET | `/api/v1/workspaces/default` | `{ "workspace": {...} }` |
| GET | `/api/v1/projects?workspace_slug=default` | `{ "projects": [...] }` |
| GET | `/api/v1/projects/default` | `{ "project": {...} }` |

Returns **503** when Postgres platform metadata is not configured.

### M2A document endpoints (same Postgres requirement)

| Method | Path | Notes |
|--------|------|--------|
| POST | `/api/v1/libraries` | JSON `{ name, description?, project_id? }` |
| GET | `/api/v1/libraries` | `{ "libraries": [...] }` |
| GET | `/api/v1/libraries/{id}` | |
| DELETE | `/api/v1/libraries/{id}` | 409 if documents remain |
| POST | `/api/v1/libraries/{id}/documents` | `multipart/form-data` field `file` |
| GET | `/api/v1/libraries/{id}/documents` | |
| GET | `/api/v1/documents/{id}` | `storage_path` omitted in JSON |
| DELETE | `/api/v1/documents/{id}` | 500 if binary delete fails (metadata retained) |
| POST | `/api/v1/documents/{id}/process` | Re-queue ingestion (background); idempotent |

Upload returns `status=QUEUED` and enqueues processing when `DOCUMENT_AUTO_PROCESS=true`.

Document JSON exposes `processing_stage`, `error_summary`, `chunk_count` (not `storage_path`).

### M2C retrieval (Postgres + Qdrant)

| Method | Path | Notes |
|--------|------|--------|
| POST | `/api/v1/retrieval/search` | JSON `{ query, project_id?, library_ids?, document_ids?, top_k? }` |

Response:

```json
{
  "query": "string",
  "results": [{ "chunk_id", "document_id", "library_id", "text", "filename", "page_number", "section", "vector_score", "rerank_score", "metadata" }],
  "citations": [{ "document_id", "filename", "page_number", "section", "chunk_id", "source_uri", "snippet", "score" }],
  "context": { "total_candidates", "selected_candidates", "token_budget_used" },
  "metadata": { "embedding_model", "embedding_dimension", "reranker_model", "rerank_fallback", "embedding_ms", "vector_search_ms", "rerank_ms", "context_build_ms", "total_retrieval_ms" }
}
```

Errors: structured `{ "detail": { "code", "message" } }` — e.g. `qdrant_unavailable` (503), `dimension_mismatch` (409), `forbidden` cross-project (403).

**Not connected to `/chat` or `/chat/stream` in M2C.**

### AskDataRequest (current)

```json
{
  "session_id": "uuid",
  "question": "string",
  "provider": "qwen|gemini|openai",
  "model": "string",
  "use_local_agent": false,
  "mode": "ask_data",
  "library_ids": ["uuid"]
}
```

- `mode` defaults to **`ask_data`** — existing clients unchanged.
- `mode=rag` requires Postgres + knowledge stack; optional `library_ids` scope RAG sources.

`AskDataResponse` optional extensions for RAG: `route`, `grounding`, `citations[]`, `retrieval{ candidate_count, selected_count }`.

### M2D RAG query (non-stream)

| Method | Path | Notes |
|--------|------|--------|
| POST | `/api/v1/rag/query` | JSON `{ query, project_id?, library_ids?, conversation_id?, provider, model? }` |

### AskDataResponse (current)

Fields in `backend/app/core/models.py`:

- `request_id`, `session_id`, `status` (`SUCCESS|CLARIFICATION|NO_DATA|UNSUPPORTED|ERROR`)
- `strategy` (`governed|sql_fallback|clarification|unsupported|conversational|...`)
- `answer`: `AnalysisOutput` (direct_answer, executive_summary, insights, business_implications, caveats, data_reference, chart_spec)
- `data`: columns, rows, row_count, execution_ms, governed_metric, unit_format; optional safe datasource fields `connector_type`, `connector_name` (C5)
- `chart_spec`, `timings`, `retry_count`, `usage`, `governed_sql`

## SSE contract (current)

`POST /chat/stream` → `text/event-stream`

- Heartbeat: `: keep-alive` every 15s
- Data lines: JSON object

**Progress event:**

```json
{
  "type": "progress",
  "stage": "string",
  "label": "string",
  "detail": "string|null"
}
```

**Terminal event:**

```json
{
  "type": "done",
  "response": { /* AskDataResponse */ }
}
```

v3 proxy may emit upstream events — treat as implementation detail until unified.

## Prompts (M3A — implemented)

Requires `STATE_STORE=postgres` and platform seed (same as Knowledge APIs).

| Method | Path | Notes |
|--------|------|--------|
| GET | `/api/v1/prompts` | Query: `scope`, `search`, `project_id` |
| POST | `/api/v1/prompts` | Create prompt + initial **draft** version |
| GET | `/api/v1/prompts/{id}` | |
| GET | `/api/v1/prompts/{id}/versions` | Newest first |
| POST | `/api/v1/prompts/{id}/versions` | Body `{ "content", "created_by?" }` → DRAFT |
| POST | `/api/v1/prompts/{id}/versions/{version_id}/publish` | Activates version; archives prior ACTIVE |
| POST | `/api/v1/prompts/{id}/versions/{version_id}/rollback` | Re-activate archived version |
| POST | `/api/v1/prompts/resolve` | Body `{ "prompt_key", "project_id?" }` — effective preview |

Keys: `ask_data.system`, `rag.system`, `rag.insufficient_evidence`.

## Semantic registry (S1 — implemented)

Prefix: `/api/v1/semantic` (Postgres + platform seed required).

| Method | Path | Notes |
|--------|------|--------|
| GET/POST | `/models` | List/create semantic models (per project) |
| GET/PATCH | `/models/{id}` | |
| GET/POST | `/models/{id}/versions` | |
| GET | `/versions/{id}` | |
| POST | `/versions/{id}/clone` | Clone to new DRAFT |
| POST | `/versions/{id}/validate` | Body `{ mode?: structural|source|full, source_mode?: metadata_only|safe_query }` → readiness, summary, issues_by_category, run_id |
| GET | `/versions/{id}/readiness` | activation_readiness, last_validation_run_id |
| GET | `/versions/{id}/validation-runs` | Recent runs |
| GET | `/validation-runs/{run_id}` | Run + issues |
| GET | `/versions/{id}/diff?against=` | added/changed/removed + breaking_changes |
| GET | `/validators/health` | Impala/Trino validator connectivity |
| POST | `/versions/{id}/publish` | Blocked on validation ERROR |
| POST | `/versions/{id}/rollback` | Re-activate archived version |
| POST | `/versions/{id}/artifact-preview` | OSSIE YAML preview + checksum |
| GET | `/resolve?semantic_model_key=` | Active model + version |
| GET/POST | `/versions/{id}/entities` | POST DRAFT only |
| PATCH | `/versions/{id}/entities/{entity_id}` | DRAFT only |
| GET/POST | `/versions/{id}/metrics` | Full fields on GET (S2) |
| PATCH | `/versions/{id}/metrics/{metric_id}` | DRAFT only |
| GET/POST | `/versions/{id}/dimensions` | |
| PATCH | `/versions/{id}/dimensions/{dimension_id}` | |
| GET/POST | `/versions/{id}/relationships` | |
| PATCH | `/versions/{id}/relationships/{relationship_id}` | |
| GET/POST | `/versions/{id}/terms` | |
| PATCH | `/versions/{id}/terms/{term_id}` | |
| GET | `/import/source` | Detected OSSIE path for current project |
| POST | `/import` | Body `{ model_key, model_name?, dry_run? }` — OSSIE → DRAFT (409 if draft exists) |

Bootstrap: `python scripts/import_ossie_semantics.py` or `POST /import` (read-only OSSIE import → DRAFT).

**S2 UI:** `/semantic-layer` in `frontend/` (`NEXT_PUBLIC_FEATURE_SEMANTIC_LAYER`). Publish updates registry ACTIVE only — use S4 runtime APIs to activate Ask Data OSSIE.

### S4 — Runtime activation

| Method | Path | Notes |
|--------|------|--------|
| GET | `/runtime/status` | `registry_active_version`, `runtime_active_version`, `deployment`, `loader_mode` |
| GET | `/runtime/deployments` | History (`model_key`, `limit`) |
| GET | `/runtime/deployments/{id}` | Deployment + lifecycle events |
| POST | `/versions/{id}/runtime/stage` | Generate immutable OSSIE artifact → STAGED deployment |
| POST | `/runtime/deployments/{id}/validate` | YAML/checksum pre-check |
| POST | `/runtime/deployments/{id}/smoke` | OSSIE resolver smoke |
| POST | `/runtime/deployments/{id}/activate` | `?dry_run=true` → `READY_TO_ACTIVATE` without pointer change |
| POST | `/runtime/deployments/{id}/rollback` | Prior ACTIVE/SUPERSEDED deployment only |

Ask Data responses may include `semantic_runtime` metadata (mode, deployment_id, registry version, checksum).

See [SEMANTIC_RUNTIME_ACTIVATION.md](./SEMANTIC_RUNTIME_ACTIVATION.md).

## Connectors (C1 — implemented)

| Method | Path | Notes |
|--------|------|--------|
| GET | `/connectors` | Project-scoped list (`connector_type`, `enabled`) |
| POST | `/connectors` | Create (`impala` \| `trino` \| `postgres`) |
| GET | `/connectors/{id}` | Safe config + `credentials_configured` |
| PATCH | `/connectors/{id}` | Update config/metadata/secret_ref |
| DELETE | `/connectors/{id}` | Blocked if `default_connector_id` reference |
| POST | `/connectors/{id}/test` | On-demand connection test |
| GET | `/connectors/{id}/capabilities` | Adapter capability flags |
| GET | `/connectors/{id}/catalogs` | Trino (when supported) |
| GET | `/connectors/{id}/schemas` | Optional `catalog` query |
| GET | `/connectors/{id}/tables` | `catalog`, `schema`, `table_type`, `search`, `limit`, `offset`, `refresh` |
| GET | `/connectors/{id}/metadata/summary` | Bounded source overview counts |
| POST | `/connectors/{id}/metadata/describe` | Body `{ catalog?, schema?, table }` → `TableDetail` |
| POST | `/connectors/{id}/metadata/preview` | Body `{ catalog?, schema?, table, limit? }` → safe sample rows |
| GET | `/connectors/{id}/references` | Semantic entities referencing connector (C4) |

Connection test (`POST .../test`) returns `phases`, `default_catalog`, `default_schema`, `error_code`, and API-shaped `capabilities`.

### Semantic entity import (C4)

| Method | Path | Notes |
|--------|------|--------|
| POST | `/semantic/versions/{id}/entities/import-preview` | Connector table → candidate dimensions + duplicate check |
| POST | `/semantic/versions/{id}/entities/import` | Create entity + optional dimensions on **DRAFT** only |

Entity payloads include optional `connection_id` (safe — no secrets).

Secrets: `secret_ref` uses `env://VAR` — never returned in plaintext. External PostgreSQL connectors are **not** `DATABASE_URL`.

See [CONNECTOR_DESIGN.md](./CONNECTOR_DESIGN.md).

## Skills (M3B — implemented)

| Method | Path | Notes |
|--------|------|--------|
| GET | `/api/v1/skills` | Query: `scope`, `search`, `project_id` |
| POST | `/api/v1/skills` | Create skill + initial draft version |
| GET | `/api/v1/skills/{id}` | |
| GET | `/api/v1/skills/{id}/versions` | |
| POST | `/api/v1/skills/{id}/versions` | New DRAFT version |
| POST | `/api/v1/skills/{id}/versions/{version_id}/publish` | |
| POST | `/api/v1/skills/{id}/versions/{version_id}/rollback` | |
| POST | `/api/v1/skills/{id}/execute` | Body `{ "input", "conversation_id?", "context?" }` — **active version only** |
| GET | `/api/v1/tools` | ToolRegistry metadata for UI |

## Target `/api/v1` groups (design)

| Group | Endpoints (illustrative) |
|-------|---------------------------|
| workspaces | `GET/POST /api/v1/workspaces`, `GET/PATCH /api/v1/workspaces/{id}` |
| projects | `.../projects`, bind OSSIE path, default connectors |
| chat | Optional aliases only — **primary chat remains** `/chat`, `/chat/stream` |
| conversations | `GET/DELETE .../conversations`, messages pagination |
| models | `GET /api/v1/models` |
| documents | `POST .../documents/upload`, `GET .../documents/{id}` |
| libraries | CRUD + reindex |
| connectors | CRUD, `POST .../test`, `POST .../sync` |
| prompts | CRUD versions, `POST .../activate` |
| skills | CRUD versions, `POST .../activate` |
| usage | summary, events, export |
| audit | `GET .../audit/events` (admin) |

## Unified AI response (target — not M1 FE migration)

Long term, clients should not branch on internal engine. Proposed superset **`UnifiedAIResponse`**:

```json
{
  "status": "success|clarification|error|no_data",
  "route": "ask_data|rag|hybrid|general|clarification",
  "request_id": "uuid",
  "session_id": "uuid",
  "answer": { "direct_answer": "", "executive_summary": "", "insights": [], "business_implications": [], "caveats": [] },
  "data": { "columns": [], "rows": [], "row_count": 0 },
  "visualization": { "chart_spec": null },
  "citations": [],
  "analysis_document": { "sections": [], "governed_sql": null },
  "clarification": { "question": null, "options": [] },
  "execution_metadata": { "timings": {}, "usage": {}, "strategy": "", "retry_count": 0 },
  "error": { "code": null, "message": null, "safe_message": null }
}
```

**M1 policy:**

- **`AskDataResponse`** on `/chat` and `/chat/stream` remains **unchanged** and is what `frontend` uses.
- **`UnifiedAIResponse`** is documented for future RAG/hybrid clients; backend may add an optional mapper or `/api/v1` responses later **without** forcing FE migration in M1.
- When mapping exists, `AskDataResponse` maps 1:1 into UnifiedAIResponse (empty `citations` until RAG).

## Target SSE events (design)

| type | Purpose |
|------|---------|
| `heartbeat` | keep-alive (optional rename from comment line) |
| `thinking` | optional LLM reasoning indicator |
| `progress` | stage updates (keep current) |
| `clarification` | mid-stream clarify |
| `data` | partial table preview (future) |
| `analysis` | partial narrative (future) |
| `visualization` | chart spec ready |
| `completed` | final unified response |
| `error` | terminal failure |

Preserve compatibility: clients ignoring unknown `type` values.

## Errors

- HTTP 422 — invalid model/provider selection
- HTTP 503 — `/health/ready` not ready
- HTTP 200 + `status: ERROR` — user-safe message in `answer` (data backend failures)

Codes: `IMPALA_*`, `DUCKDB_QUERY_FAILED`, internal `UNEXPECTED`.

## Frontend proxy

Browser → `GET/POST /api/*` → Next rewrite → `BACKEND_API_URL`.

See `frontend/next.config.mjs`.

Legacy doc `docs/api-contract-v2.md` describes an older dashboard/chat shape — **not** the current Ask Data v2 contract.
