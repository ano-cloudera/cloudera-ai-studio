# Post-migration standalone stabilization report

**Milestone:** `POST_MIGRATION_STANDALONE_STABILIZATION`  
**Date:** 2026-10-18  
**Canonical repo:** `~/Documents/Works/cloudera/cloudera-ai-studio`  
**Old repo:** `enterprise-ai-poc` — **read-only, untouched**

## Executive summary

Two migration-related configuration bugs caused **split document storage** and **unresolved semantic runtime paths**. A **broken frontend lifecycle script** left stale Next.js processes serving **HTTP 500** on port 3001. All were fixed with minimal diffs; no new features; Golden Banking Phase 1 remains **PASS**.

## Errors found and fixed

| ID | Issue | Fix |
|----|--------|-----|
| PM-001 | Double `backend/` in document storage root | `_resolve_backend_relative()` + env template updates |
| PM-002 | Semantic runtime path not absolutized | Same helper + env updates |
| PM-003 | `dev-frontend.sh` could not stop/restart dev server | Lifecycle script aligned with backend pattern |

See full records: [`POST_MIGRATION_ERROR_INVENTORY.md`](./POST_MIGRATION_ERROR_INVENTORY.md).

## Migration-related root causes

1. **Monorepo env templates** used paths like `backend/runtime/...` meaning “from repo root,” but standalone **`BACKEND_ROOT` is already `…/backend`**, producing `backend/backend/…`.
2. **Incomplete standalone dev ergonomics** for frontend stop/start after directory rename (`frontend-dev` → `frontend`).

## Tests and builds

| Check | Result |
|-------|--------|
| Backend `make test-backend` | **428 passed**, 85 skipped, 4 deselected |
| Frontend Vitest | **225 passed** (52 files) |
| Frontend `npm run build` | **PASS** |
| Alembic | Single head `m9_chat_attachments_001` |
| Golden Banking Phase 1 | **6 passed** (`GOLDEN_BANKING_RUN_INTEGRATION=1`) |
| Browser smoke | **STANDALONE_BROWSER_SMOKE_PASS** |
| Isolation audit | **ISOLATION_AUDIT_PASS_NON_DESTRUCTIVE** |

## Runtime verification

- `/health` → 200  
- `/health/ready` → `core_ready: true`, postgres + qdrant ready  
- Primary UI routes → HTTP 200 after `./scripts/dev-frontend.sh restart`  
- **Zero runtime imports/paths** to `enterprise-ai-poc` (active `.venv` is standalone)

## Evidence

`testing/evidence/post-migration-stabilization/`

- `backend-health.json`, `backend-ready-after-fix.json`
- `api-smoke.json`, `api-smoke-status.txt`
- `browser-smoke.log` (PASS)
- `isolation-audit.txt`

## Unresolved / low-priority risks

1. **Orphan blobs** under `backend/backend/runtime/document_storage` (~52K) from pre-fix uploads — safe to delete manually after confirming no needed docs (main corpus under `backend/runtime/document_storage`).
2. **Next.js `allowedDevOrigins` warning** (PM-005) — cosmetic in dev.
3. **Operational:** UI shows “Platform Unavailable” when backend on :8001 is stopped — expected.

## Golden Banking Phase 1

**Status: PASS** — connector/raw Ask tests unchanged; no reseed performed.

## Old repository safety

No modifications, moves, or service starts from `enterprise-ai-poc`. Isolation audit passed non-destructively.

## How to run standalone (canonical)

```bash
cd ~/Documents/Works/cloudera/cloudera-ai-studio
./scripts/dev-backend.sh start
./scripts/dev-frontend.sh start   # or restart
```

Ensure `.env` uses backend-relative storage paths:

- `DOCUMENT_STORAGE_ROOT=runtime/document_storage`
- `SEMANTIC_RUNTIME_STORAGE_ROOT=var/semantic-runtime`

Restart backend after changing `.env`.
