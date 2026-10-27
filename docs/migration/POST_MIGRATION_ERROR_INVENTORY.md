# Post-migration error inventory

**Milestone:** `POST_MIGRATION_STANDALONE_STABILIZATION`  
**Repo:** `cloudera-ai-studio` only  
**Captured:** 2026-10-18

---

## PM-001

| Field | Value |
|-------|--------|
| **ID** | PM-001 |
| **Surface** | CONFIG / FILESYSTEM |
| **Exact symptom** | Knowledge uploads and readiness reported storage under `backend/backend/runtime/document_storage` while real files lived under `backend/runtime/document_storage`. |
| **Exact error** | `/health/ready` → `document_storage.path` = `…/backend/backend/runtime/document_storage` |
| **Reproduction** | Set `DOCUMENT_STORAGE_ROOT=backend/runtime/document_storage` (from monorepo-style env), start backend, call `/health/ready`. |
| **Root cause** | `get_settings()` joins relative paths with `BACKEND_ROOT` (`…/backend`) without stripping a redundant `backend/` prefix copied from monorepo templates. |
| **Migration-related?** | **YES** |
| **Severity** | **P2** (wrong storage root; split blobs / empty Knowledge after migration) |
| **Fix** | `_resolve_backend_relative()` in `backend/app/core/config.py`; normalize `.env`, `deployment/profiles/local.env`, `config/examples/accelerator.env.example` to `runtime/document_storage`. |
| **Validation** | `pytest backend/tests/test_standalone_path_resolution.py`; `/health/ready` shows single `backend/runtime/document_storage`. |

---

## PM-002

| Field | Value |
|-------|--------|
| **ID** | PM-002 |
| **Surface** | CONFIG / FILESYSTEM |
| **Exact symptom** | Semantic runtime storage path stayed relative (`backend/var/semantic-runtime`) and was not resolved under `BACKEND_ROOT`. |
| **Exact error** | Readiness JSON showed `"path": "backend/var/semantic-runtime"` (relative). |
| **Reproduction** | `SEMANTIC_RUNTIME_STORAGE_ROOT=backend/var/semantic-runtime` + inspect `get_settings().semantic_runtime_storage_root`. |
| **Root cause** | Only `document_storage_root` and `duckdb_path` were absolutized; semantic runtime was not. |
| **Migration-related?** | **YES** |
| **Severity** | **P2** |
| **Fix** | Same `_resolve_backend_relative()` applied to `semantic_runtime_storage_root`; env templates updated to `var/semantic-runtime`. |
| **Validation** | Path test + readiness shows absolute path under `backend/var/semantic-runtime`. |

---

## PM-003

| Field | Value |
|-------|--------|
| **ID** | PM-003 |
| **Surface** | FRONTEND / STARTUP |
| **Exact symptom** | All primary routes returned **HTTP 500** while an old `next-server` process still held port 3001. |
| **Exact error** | `curl -sf http://127.0.0.1:3001/` → exit 22 (HTTP 500); `./scripts/dev-frontend.sh` → `EADDRINUSE`. |
| **Reproduction** | Leave stale dev server running after `.next` invalidation or failed restart; hit `/`, `/knowledge`. |
| **Root cause** | Root `scripts/dev-frontend.sh` used bare `exec npm run dev` with no stop/restart lifecycle (unlike `dev-backend.sh`). |
| **Migration-related?** | **YES** (standalone lifecycle scripts incomplete after rename) |
| **Severity** | **P1** |
| **Fix** | Replaced `scripts/dev-frontend.sh` with start/stop/restart/status/logs using `frontend/scripts/lib/frontend-dev-common.sh`. |
| **Validation** | `./scripts/dev-frontend.sh restart` → GET `/`, `/knowledge`, `/connectors` HTTP 200. |

---

## PM-004

| Field | Value |
|-------|--------|
| **ID** | PM-004 |
| **Surface** | FRONTEND / KNOWLEDGE |
| **Exact symptom** | Knowledge page showed “Platform Unavailable” / “Unable to load libraries” or long “Loading knowledge libraries…”. |
| **Exact error** | UI error state when backend on :8001 down or not reachable via proxy. |
| **Reproduction** | Stop backend; open `http://127.0.0.1:3001/knowledge`. |
| **Root cause** | Operational dependency on backend health (not a standalone routing bug). |
| **Migration-related?** | **NO** (expected degraded UX) |
| **Severity** | **P1** when backend down |
| **Fix** | Use `./scripts/dev-backend.sh start` before UI smoke; no product change required. |
| **Validation** | Backend up → Knowledge lists libraries; browser smoke `knowledge_table` PASS. |

---

## PM-005

| Field | Value |
|-------|--------|
| **ID** | PM-005 |
| **Surface** | FRONTEND |
| **Exact symptom** | Next.js dev console warning about cross-origin requests from `127.0.0.1` to `/_next/*`. |
| **Exact error** | `Cross origin request detected from 127.0.0.1… configure allowedDevOrigins` |
| **Reproduction** | Open app via `127.0.0.1:3001` while dev server binds `0.0.0.0`. |
| **Root cause** | Next.js 15 dev-origin check. |
| **Migration-related?** | **NO** |
| **Severity** | **P5** |
| **Fix** | Deferred (warning only; no crash). |
| **Validation** | N/A |

---

## PM-006

| Field | Value |
|-------|--------|
| **ID** | PM-006 |
| **Surface** | BACKEND |
| **Exact symptom** | Smoke probe `GET /api/v1/sessions` and `GET /api/v1/usage/summary` return 404. |
| **Exact error** | HTTP 404 |
| **Reproduction** | `curl http://127.0.0.1:8001/api/v1/sessions` |
| **Root cause** | No such v1 routes; chat sessions use `/chat/sessions/{id}`; usage may be under different path. |
| **Migration-related?** | **NO** (incorrect probe path in manual smoke) |
| **Severity** | **P5** |
| **Fix** | Document correct routes in smoke checklist (no code change). |
| **Validation** | `/health`, `/api/v1/libraries`, `/api/v1/connectors`, etc. return 200. |

---

## Old repository dependency scan (summary)

| Class | Count | Notes |
|-------|-------|--------|
| **A — forbidden runtime** | **0** in `backend/app`, `frontend/src`, runtime scripts |
| **B — documentation** | Multiple refs in `docs/migration/*`, `PROJECT_STATE.md` |
| **C — test/fixture** | Isolation audit scripts reference old path intentionally |
| **D — migration artifact** | `.venv.monorepo-symlink-backup-20261018/` (not active venv) |

**Isolation:** `ISOLATION_AUDIT_PASS_NON_DESTRUCTIVE` (see `testing/evidence/post-migration-stabilization/isolation-audit.txt`).
