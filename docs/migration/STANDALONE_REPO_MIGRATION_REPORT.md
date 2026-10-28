# Standalone repository migration report

**Source (reference only — do not modify for extraction):** `~/Documents/Works/cloudera/enterprise-ai-poc`  
**Target:** `~/Documents/Works/cloudera/cloudera-ai-studio`  
**Strategy:** COPY → NORMALIZE → TEST → PROVE (see `SOURCE_EXTRACTION_POLICY.md`)

## Closure verdict (2026-10-18)

**CLOUDERA_AI_STUDIO_STANDALONE_REPO_PASS**

Evidence roots:

- Browser: `testing/evidence/standalone/BROWSER_SMOKE/standalone_browser_smoke.json`
- Isolation: `testing/evidence/standalone/ISOLATION/result.txt`

## Eight historical backend failures — triage

Re-run default suite: **408 passed, 85 skipped, 4 deselected** (`backend/pytest.ini`).

| Test | Failure (historical) | Root cause | Class | Fix / action | Final |
|------|----------------------|------------|-------|--------------|-------|
| `test_stores_factory.py` (2) | Postgres stores when SQLite expected | `.env` / shell `STATE_STORE` + `DATABASE_URL` leaked into `Settings()` | **C** env-dependent | `isolated_settings` / `model_construct`; autouse env scrub in `conftest.py` | PASS |
| `test_models_api.py` readiness (2) | Expected `impala` component | Readiness model uses `legacy_datasource`; core ready with LLM only | **D** stale | Assert `legacy_datasource`, HTTP 200 | PASS |
| `test_models_api.py` GSSAPI | `KeyError: 'impala'` | Same readiness shape drift | **D** | Assert `legacy_datasource == ready` | PASS |
| `test_chat_api.py` (2 stream) | 422 unknown model | Registry + env bleed | **C/D** | `client()` uses `isolated_settings`; registered model id | PASS |
| `test_c5_physical_identifiers.py` | Postgres quoting | Product uses unquoted `public.sales_monthly` | **D** | Update expectation | PASS |
| `test_semantic_context.py` (2 promo ROI) | Tempo OSSIE metric drift | Demo-specific routing | **D** tempo | `@pytest.mark.tempo_domain`; excluded from default suite | Skipped in default |

No **A** extraction regressions remained after `.venv` localization (see below).

## Default backend test contract

| Marker | Meaning |
|--------|---------|
| *(default)* | `-m "not tempo_domain and not integration"` in `backend/pytest.ini` |
| `tempo_domain` | Reference-project OSSIE-specific semantic expectations — `make test-backend-tempo` |
| `integration` | External DB / infra — `make test-backend-integration` |

Impala/Kerberos: **not** required for the default deterministic suite. Live Impala remains env-driven at runtime, not in unit pytest defaults.

## Database URL contract

| Context | `STATE_STORE` / `DATABASE_URL` | Notes |
|---------|-------------------------------|--------|
| **Unit tests** | `sqlite` + empty `DATABASE_URL` | Forced in `backend/tests/conftest.py` before app import |
| **Local development** | From root `.env` (typically `postgres` + Docker Postgres e.g. `127.0.0.1:55432`) | Normal `./scripts/dev-backend.sh start` loads `deployment/profiles/runtime-closure.env` then `.env` |
| **Fresh migration proof** | Same Docker smoke DB (`m1-pg-smoke` / `cai_studio_fresh_mig`) | One-time proof; **not** required if dev uses sqlite-only mode |
| **Alembic CLI** | Requires same env as dev when using Postgres | `source` profile + `.env` before `alembic current` |

Smoke migration DB is **not** required for everyday startup when `STATE_STORE=sqlite`.

## Legacy environment defaults audit

| Value | Location | Classification |
|-------|----------|----------------|
| `reference_impala` | `backend/app/core/config.py` default slug | **Demo/reference OSSIE** bundled under `backend/projects/reference_impala/` |
| `reference_impala` | `config/examples/accelerator.env.example` | **Example profile** — override with `example_project` for neutral PoC |
| `reference_impala` | `tests/conftest.py` | **Test fixture** slug for deterministic OSSIE paths |
| `ai-studio-*.pdf` | `frontend/src/lib/chatPdfExport.ts` | **Export filename prefix** (cosmetic; not product name) |

Generic UI naming uses `APP_NAME` / `NEXT_PUBLIC_APP_NAME` from env. No runtime references to `enterprise-ai-poc`, `backend-dev`, or `frontend-dev` under `backend/app`, `frontend/src`, or `scripts/lib`.

## Extraction fix: local Python venv

Early standalone `.venv` incorrectly symlinked into the source monorepo when created under an active `VIRTUAL_ENV`. **Fixed:** recreate with Homebrew Python; `scripts/bootstrap/bootstrap-local.sh` detects monorepo `pyvenv.cfg` / symlink and recreates locally.

## Non-destructive isolation proof

**No** rename/move of `enterprise-ai-poc`. Proof uses:

- `./scripts/prove-old-repo-isolation.sh` — backend start, pytest sample, `sys.path` audit, listener `cwd` check
- Clean shell: `REPO_ROOT=cloudera-ai-studio`, sanitized `PATH`, `bad_sys_path []`
- Runtime grep: **zero** hits in `backend/app`, `frontend/src`, `scripts/lib`

## Final verification matrix (2026-10-18 run)

| Gate | Status |
|------|--------|
| Backend deterministic suite | **PASS** (408 passed) |
| 8 previous failures resolved/classified | **PASS** |
| Impala/Kerberos test contract | **PASS** |
| Store factory | **PASS** |
| Semantic context | **PASS** (default suite; tempo_domain optional) |
| Legacy env audit | **PASS** (documented) |
| DB config contract | **PASS** (documented) |
| Standalone API | **PASS** |
| Standalone browser smoke | **PASS** (`STANDALONE_BROWSER_SMOKE_PASS`) |
| Hydration readiness | **PASS** (`hydration_readiness` + HTTP stack gates) |
| No fatal console errors | **PASS** |
| Non-destructive isolation proof | **PASS** (`ISOLATION_AUDIT_PASS_NON_DESTRUCTIVE`) |
| Zero unintended old-repo runtime references | **PASS** |
| Full Vitest | **PASS** (220/220) |
| Frontend build | **PASS** |
| Alembic clean | **PASS** (single head `m9_chat_attachments_001`) |
| Source repo untouched by closure task | **PASS** (read-only git audit only) |
| Migration report updated | **PASS** |

## Migrated layout (unchanged)

| Source | Target |
|--------|--------|
| `backend-dev/` | `backend/` |
| `frontend-dev/` | `frontend/` |
| Shared config/deployment/scripts/docs | Copied / trimmed per dependency map |

See `STANDALONE_REPO_DEPENDENCY_MAP.md` for full classification.
