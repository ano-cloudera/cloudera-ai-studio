# PostgreSQL Data Model (proposed)

**Status:** M1 + M2A + **M2B** in `backend/` — migrations through `m2b_chunks_001`. See [M2_DOCUMENT_INTELLIGENCE.md](../architecture/M2_DOCUMENT_INTELLIGENCE.md).

## Conventions

- UUID primary keys (`gen_random_uuid()`)
- `created_at`, `updated_at` timestamptz
- Soft delete optional (`deleted_at`) for user-facing entities
- All tenant-scoped tables include `workspace_id`; project-scoped include `project_id`

## Entity relationship (overview)

```text
Workspace 1──* Project 1──* Conversation 1──* Message
                │
                ├──* Connector
                ├──* Prompt ──* PromptVersion
                ├──* Skill ──* SkillVersion
                ├──* Library ──* Document ──* DocumentChunk (metadata; vectors in Qdrant)
                └──* ModelConfiguration (overrides)

UsageEvent *, AuditEvent * → workspace (+ optional project, user ref)
ConnectorSyncJob * → Connector
```

## ConversationStore abstraction (M1)

Session and turn persistence **must not** be hard-coded to SQLite or Postgres.

| Implementation | When |
|----------------|------|
| `SqliteConversationStore` | Default local dev; **retained through M1** |
| `PostgresConversationStore` | Pilot/accelerator deployments (M1+) |

- Interface covers: load history by `session_id`, append turn, delete session, optional metadata (title, project binding).
- **No immediate hard cutover:** config selects implementation; data may be migrated with a one-time script when operators choose Postgres.
- **Config (ADR-008):** `STATE_STORE=sqlite` | `STATE_STORE=postgres` — ConversationStore and UsageStore both respect the same setting (or documented sub-keys if split later).
- SQLite **keeps legacy schema permanently for compatibility** (no normalization work on SQLite — ADR-007).
- Postgres uses normalized `conversation` / `message` tables when enabled.

**UsageStore** follows the same pattern with **SQLite + PostgreSQL parity** (ADR-007): one interface, two implementations, no forced cutover.

### SQLite schema policy (ADR-007)

- SQLite backends **retain existing table layouts** for compatibility (`conversation_history.sqlite`, `llm_usage.sqlite`).
- **No normalization refactor** of SQLite schema in M1 — adapters map to/from the current shape.
- PostgreSQL may use normalized `conversation` / `message` / `usage_event` tables when enabled.

## Tables (minimum)

### workspace

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| slug | text unique | Pilot: seed **`default`** workspace (ADR-007) |
| name | text | |
| settings_json | jsonb | feature flags, branding refs |

**Pilot:** single default workspace row; multi-workspace schema supported for later customers without requiring multi-tenant UI in M1.

### project

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| workspace_id | uuid FK | |
| slug | text | unique per workspace |
| name | text | |
| ossie_root_path | text | e.g. `projects/tempo_scan_impala` |
| default_connector_id | uuid FK nullable | |
| status | enum | active, archived |

### conversation

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| project_id | uuid FK | |
| external_session_id | text | maps to client `session_id` |
| title | text nullable | |
| last_message_at | timestamptz | index |

Index: `(project_id, external_session_id)` unique.

### message

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| conversation_id | uuid FK | |
| role | enum | user, assistant, system |
| content_text | text | |
| response_json | jsonb nullable | full unified response snapshot |
| route | text nullable | ask_data, rag, hybrid |
| status | text | |
| request_id | uuid nullable | index |

### model_configuration

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| project_id | uuid FK nullable | null = workspace default |
| provider | text | |
| model_id | text | |
| params_json | jsonb | temperature, max_tokens |
| is_default | bool | |

### prompt / prompt_version

**prompt**

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| workspace_id | uuid FK | **required** — all prompts belong to a workspace |
| project_id | uuid FK nullable | null = workspace-wide prompt, not tied to one project |
| slug | text | unique per `(workspace_id, project_id, slug)` with null project treated as workspace scope |
| name | text | |
| scope | text | explicit: `workspace`, `project`, `skill` (see PROMPT_DESIGN.md) |

**Scope semantics:** `workspace` does **not** mean installation-wide unless that workspace is the deployment’s root tenant. Multi-workspace pilots may each have their own “global” system prompts.

**prompt_version:** id, prompt_id, version int, body text, created_by, created_at, **is_active** bool

Unique: one active version per prompt (partial index).

### semantic registry (S1)

**semantic_models:** id, workspace_id, project_id, name, key (unique per project), active_version_id, description, timestamps

**semantic_versions:** id, semantic_model_id, version_number, status (`DRAFT`|`ACTIVE`|`ARCHIVED`), runtime artifact metadata fields, published_at

Child objects (unique `key` per version): **semantic_entities**, **semantic_metrics**, **semantic_dimensions**, **semantic_relationships**, **semantic_terms**

PostgreSQL is the **management** source of truth; OSSIE YAML on disk remains the **current runtime** artifact until future activation (S4+).

See `SEMANTIC_REGISTRY_DESIGN.md`.

### skill / skill_version

**skill:** id, project_id, slug, name, description

**skill_version:** id, skill_id, version, manifest_json (tools, permissions, output), is_active

### connector

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| project_id | uuid FK | |
| type | text | **Extensible** — validated against a **connector type registry** in code (not a closed Postgres enum). Known types include `impala`, `trino`, `duckdb_governed` (dev), `slack`, `gmail`; new types added via registry + adapter without DB migration |
| name | text | |
| config_json | jsonb | non-secret settings |
| secret_ref | text | SecretProvider key |
| status | enum | draft, active, error |
| last_tested_at | timestamptz | |

### connector_sync_job

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| connector_id | uuid FK | |
| status | enum | pending, running, succeeded, failed |
| started_at, finished_at | timestamptz | |
| stats_json | jsonb | rows/docs processed |
| error_message | text | |

### library

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| project_id | uuid FK | |
| name | text | |
| qdrant_collection | text nullable | Set when using **per-library collection** strategy; null when using shared collection + payload filters (see RAG_DESIGN.md) |
| embedding_model | text | default bge-m3 |

### document

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| library_id | uuid FK | |
| filename | text | |
| mime_type | text | |
| size_bytes | bigint | |
| nfs_uri | text | pointer only |
| status | enum | uploaded, parsing, embedding, ready, failed |
| page_count | int nullable | |
| metadata_json | jsonb | |

Index: `(library_id, status)`.

### document_chunk

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| document_id | uuid FK | |
| chunk_index | int | |
| qdrant_point_id | text | |
| page | int nullable | |
| section | text nullable | |
| char_start, char_end | int nullable | |
| token_count | int | |

Vectors stored in Qdrant payload mirrors snippet + ids.

### usage_event

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| workspace_id | uuid FK | |
| project_id | uuid FK nullable | |
| request_id | uuid | |
| session_id | text | |
| provider, model | text | |
| route, strategy, status | text | |
| prompt_tokens, completion_tokens | int | |
| created_at | timestamptz | index |

### audit_event

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| workspace_id | uuid FK | |
| actor | text | |
| action | text | |
| resource_type, resource_id | text | |
| detail_json | jsonb | |
| created_at | timestamptz | |

## SQLite → Postgres migration (M1)

| SQLite today | Postgres target |
|--------------|-------------------|
| `conversation_history.sqlite` | conversation + message (via ConversationStore) |
| `llm_usage.sqlite` | usage_event (via UsageStore, when enabled) |

**Policy:** add Postgres implementations **without** mandatory cutover. Operators enable Postgres when ready; SQLite remains supported for local dev and rollback.
