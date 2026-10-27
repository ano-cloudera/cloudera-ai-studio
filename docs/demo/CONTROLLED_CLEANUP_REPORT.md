# Controlled demo environment cleanup — report

**Milestone:** `CONTROLLED_DEMO_ENVIRONMENT_CLEANUP`  
**Repository:** `~/Documents/Works/cloudera/cloudera-ai-studio` only  
**Database:** `127.0.0.1:55432/accelerator` (platform metadata; no external DB/table drops)

## Summary

Application metadata was reset to a Golden Demo–ready baseline: empty Knowledge/Semantic/Data Sources in the UI, baseline Prompts/Skills only, AI Model Registry preserved, single default project retained.

## Pre-cleanup → post-cleanup counts

| Domain | Pre | Post | Notes |
|--------|----:|-----:|-------|
| Projects | 109 | 1 | Kept `tempo_scan_impala` |
| Knowledge libraries (total) | 235 | 1 | Hidden `__cai_chat_attachments__` only |
| User-facing libraries (API list) | 229 | 0 | Attachment library hidden from list |
| Semantic models | 441 | 0 | Runtime deployments cleared first |
| Data Source connectors | 143 | 0 | Connection records only |
| Prompts | 184 | 3 | Global baseline keys only |
| Skills | 161 | 2 | Ask Data Analyst + Document Q&A |
| Conversations | 371 | 0 | Scoped per cleaned projects |
| AI models (registry) | 59 | 59 | **Preserved** |
| Usage events | 371+ | 371 | 2 events removed with disposable test projects only; default-project history retained |

Evidence:

- `testing/evidence/demo-cleanup/pre-cleanup-inventory.json`
- `testing/evidence/demo-cleanup/post-cleanup-inventory.json`
- Inventory doc: `docs/demo/CLEANUP_INVENTORY.md`

## Tooling

Script: `scripts/demo-cleanup.py`

```bash
# Dry-run (default)
PYTHONPATH=backend python scripts/demo-cleanup.py --dry-run

# Apply (local DB only)
PYTHONPATH=backend python scripts/demo-cleanup.py --apply --confirm-local-db
```

Safety guards: refuses non-local `DATABASE_URL`, refuses paths under `enterprise-ai-poc`, prints DB identity, no secret export.

Deletion paths:

- Libraries: `LibraryService.delete_library` (document cascade)
- Connectors: `ConnectorRegistryService.delete_connector`
- Semantic: ORM cascade after explicit runtime deployment teardown
- Prompts/skills: ORM with `active_version_id` cleared
- Disposable projects: scoped purge of project AI assignments/models/providers + usage events, then project row

## Preserved (class A)

- Global prompts: `ask_data.system`, `rag.system`, `rag.insufficient_evidence`
- Workspace skills: `ask_data_analyst`, `document_qa`
- Chat attachment library infrastructure (`__cai_chat_attachments__`)
- Workspace/global AI Model Registry (providers, models, assignments not tied to deleted test projects)
- Alembic migration metadata

## Validation

| Gate | Result |
|------|--------|
| API: libraries / semantic / connectors empty | PASS |
| API: 3 prompts, 2 skills | PASS |
| AI models count unchanged | PASS |
| Backend restart persistence | PASS (dry-run 0 deletions after restart) |
| Backend pytest (`make test-backend`) | 408 passed |
| Vitest (`make test-frontend`) | 220 passed |
| Frontend production build | PASS (after stopping dev + `rm -rf .next`) |
| Standalone browser smoke | `STANDALONE_BROWSER_SMOKE_PASS` |
| `enterprise-ai-poc` modified by this milestone | **No** (read-only reference) |

## Known limitations

- **Project deletion** requires removing project-scoped AI registry rows and usage events; workspace/global registry entries remain.
- **Prompt/skill DELETE HTTP routes** are not exposed; cleanup uses service/ORM paths in `scripts/demo-cleanup.py`.
- **Frontend build** must not run concurrently with `next dev` on `:3001` (stale chunk risk).
- **Golden Banking Demo** seeding was intentionally **not** run in this milestone.

## Next milestone

`GOLDEN_PATH_BANKING_DEMO` — seed only after explicit go-ahead.
