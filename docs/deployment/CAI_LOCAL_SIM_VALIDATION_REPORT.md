# CAI local simulation validation report

**Milestone:** `CAI_LOCAL_SIM_VALIDATION`  
**Date:** 2026-10-19  
**Repo:** `cloudera-ai-studio` (standalone)

## Architecture validated

```text
Frontend (:3001, Next.js rewrites → BACKEND_API_URL)
    ↓
Backend (:8001, single uvicorn process, UVICORN_WORKERS=1)
    ├─ SQLite metadata: runtime/cai-sim/metadata/studio.db
    ├─ Documents:       runtime/cai-sim/documents/
    ├─ Semantic artifacts: runtime/cai-sim/semantic/
    ├─ Qdrant:          http://127.0.0.1:6333 (separate process)
    ├─ Banking PostgreSQL (connector → banking_demo.*) — external data source
    └─ LLM keys from root `.env` (not stored in SQLite)
```

## Startup commands

```bash
# Terminal 1 — Qdrant (existing local process)
# Terminal 2
./scripts/dev-cai-sim-backend.sh start
# Terminal 3
./scripts/dev-frontend.sh start
```

Seeds (once per fresh SQLite DB):

```bash
python scripts/demo/register_banking_connector.py
python scripts/demo/register_banking_knowledge.py
```

Automated orchestration:

```bash
./scripts/demo/run_cai_local_sim_validation.sh
```

## Configuration evidence

Captured in `testing/evidence/cai-local-sim-validation/runtime-config.json`:

- `metadata_database.dialect` = **sqlite**
- `core_ready` = **true**
- `DATABASE_URL` = `sqlite+pysqlite:////…/runtime/cai-sim/metadata/studio.db`
- `UVICORN_WORKERS` = **1**
- Storage paths under `runtime/cai-sim/`

### Fix applied during validation

`scripts/dev-backend.sh` re-loaded root `.env` and overwrote SQLite `DATABASE_URL` with Postgres.  
**Resolution:** `CAI_SIM_METADATA=1` + re-apply paths in `scripts/lib/backend-common.sh` after `.env` load.

## Golden Banking gates (SQLite platform metadata)

| Gate | Result |
|------|--------|
| Phase 1 | **PASS** (`GOLDEN_PATH_BANKING_DEMO_PHASE1_PASS`) |
| Phase 2 Knowledge | **PASS** (`GOLDEN_PATH_BANKING_DEMO_PHASE2_KNOWLEDGE_PASS`) |

Logs: `testing/evidence/cai-local-sim-validation/phase1-gate.log`, `phase2-gate.log`

Supporting code fixes for SQLite sim:

- Test helpers skip Postgres-only DDL on SQLite (`semantic_schema_helpers.py`, `connector_schema_helpers.py`)
- Chat / RAG / prompts use `platform_metadata_configured()` instead of `STATE_STORE=postgres` only

## Persistence & recovery

| Check | Result |
|-------|--------|
| Restart persistence (table counts) | **PASS** — `persistence-before-restart.json` == `persistence-after-restart.json` |
| Knowledge ingestion recovery (integration) | **PASS** — 6 tests in `test_knowledge_ingestion_recovery.py` |
| Concurrency probe (metadata reads) | **PASS** — `concurrency-probe.json` |
| Fresh install (disposable dir) | **PASS** — `runtime/cai-sim-disposable/metadata/studio.db` via Alembic |

## Browser & API smoke

- `backend/scripts/standalone_app_browser_smoke.py` → **PASS**  
  Evidence: `testing/evidence/cai-local-sim-validation/browser-smoke.json` (copy of standalone smoke)
- Routes: Chat, Knowledge, Semantic, Connectors, Prompts, Skills, Usage, Settings — HTTP 200, no fatal console patterns
- API checks: libraries, prompts, skills, connectors, semantic models — 200

**Note:** Browser smoke uses an already-running backend; do not run `dev-backend.sh start` during CAI sim validation (it would load Postgres `.env`). Use `dev-cai-sim-backend.sh` only.

## Qdrant

- Separate service at `QDRANT_URL=http://127.0.0.1:6333`
- With Qdrant up: readiness `qdrant.status=ready`, Phase 2 RAG gates **PASS**
- Degraded mode: readiness reports `feature_gaps` including `rag_needs_qdrant` while **`core_ready` can remain true** (backend stays up; non-RAG features available)

## Automated regression

| Suite | Result |
|-------|--------|
| Backend pytest | **433 passed**, 85 skipped |
| Frontend Vitest | **225 passed** |
| Frontend build | **PASS** |
| Postgres Alembic | **head** = `m9_chat_attachments_001` |

## Known limitations (before real CAI deploy)

1. **Single worker / single replica** — required for SQLite metadata.
2. **Local filesystem only** — not NFS/HA validated.
3. **`journal_mode=DELETE`** for SQLite (intentional local PoC).
4. **CAI_SIM env guard** — required so `.env` Postgres defaults do not override sim SQLite.
5. **Duplicate register runs** may accumulate extra connector/library rows in SQLite; gates remain pass but operators should prefer idempotent register or fresh `runtime/cai-sim` for clean demos.
6. **Browser smoke** does not replace full manual LLM chat validation; Phase 1/2 gates + API evidence cover Raw vs Knowledge routing.

## Remaining blockers before CAI deployment

- NFS-backed paths + Qdrant volume on platform
- AMP/CAI application definitions and env secret wiring
- Multi-replica backend → external PostgreSQL metadata (future HA)
- Operational backup/restore for SQLite file + document tree + Qdrant snapshots

## Evidence index

`testing/evidence/cai-local-sim-validation/` — runtime config, gates, persistence, recovery tests, browser smoke, gate summary, postgres alembic log, fresh install marker.
