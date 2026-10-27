# Phase 3 Semantic — UI & Chat Closure Report

## Root cause: `/chat` hitting Impala/DuckDB

Governed Ask executes through `RoutedQueryExecutor`. Connector-backed SQL runs only when `datasource_context` includes a `connector_id` and `runtime_mode` is `runtime` with a valid `semantic_version_id`.

Failures came from:

1. **Project scope mismatch** — structured context used `load_default_project()` while the semantic model could belong to another project. Fixed via `resolve_structured_project_scope()` (prefers `@semantic_model` owner project).
2. **Stale runtime loader settings** — singleton loader kept wrong storage paths. Fixed by updating settings on `SemanticRuntimeLoader.get()`.
3. **Missing connector on cloned versions** — `clone_version` did not copy `connection_id` on entities, so publishes after clone fell back to legacy Impala/DuckDB. Fixed in `_copy_version_content`.
4. **TestClient without lifespan** — chat tests now use `with TestClient(app)` so runtime bootstraps from SQLite.
5. **Validation gap** — publish now blocked when postgres/trino/impala entities lack `connection_id` (`missing_connector_binding`).

## Real `/chat` governed flow

Evidence: `testing/evidence/golden-path/PHASE3-SEMANTIC/chat-governed-evidence.json`

- `context_mode`: `GOVERNED_SEMANTIC`
- `strategy`: `governed`
- `connector_type`: `postgres` (Banking PostgreSQL)
- Governed SQL compiled from runtime OSSIE artifact

Script: `scripts/demo/phase3_chat_governed_evidence.py`

## Rollback proof

Evidence: `testing/evidence/golden-path/PHASE3-SEMANTIC/rollback-evidence.json`

- Version 2 created from Version 1 clone (glossary-only change), published, chat verified.
- Runtime rollback to Version 1 deployment `d4e15f94-…`.
- Post-rollback chat succeeds; **final intended runtime** = Version 1 deployment.

Script: `scripts/demo/phase3_semantic_rollback_evidence.py`

## Browser evidence

PNG captures under `testing/evidence/golden-path/PHASE3-SEMANTIC/browser/` (A–M).

Script: `scripts/demo/phase3_semantic_browser_evidence.py`

## Final active semantic runtime

After closure testing, **runtime active version = 1** (deployment `d4e15f94-1ef9-4742-85a3-329782022d3f`). Registry may show a higher published version number; governed Ask follows **runtime deployment** binding.

## Regression gates

- `scripts/demo/golden_path_banking_phase1_gate.py`
- `scripts/demo/golden_path_banking_phase2_knowledge_gate.py`
- `scripts/demo/golden_path_banking_phase3_semantic_gate.py`
- `scripts/demo/golden_path_banking_phase3_closure_gate.py` (chat + rollback + browser)

Full suite (closure run):

| Suite | Result |
|-------|--------|
| Backend pytest | 441 passed |
| Frontend Vitest | 225 passed |
| Frontend build | PASS |

Browser capture requires a healthy Next dev server on **port 3001** (`npm run dev -- -p 3001`). A stale process returning HTTP 500 will block evidence until the port is restarted; `phase3_semantic_browser_evidence.py` now kills non-ready listeners on 3001 before starting dev.
