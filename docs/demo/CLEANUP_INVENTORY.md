# Controlled demo environment — pre-cleanup inventory

**Captured:** 2026-10-18 (standalone `cloudera-ai-studio`)  
**Database:** `127.0.0.1:55432/accelerator` (platform metadata only)  
**Evidence JSON:** `testing/evidence/demo-cleanup/pre-cleanup-inventory.json`

## Runtime verification (pre-cleanup)

| Check | Result |
|-------|--------|
| Backend cwd | `cloudera-ai-studio` |
| Frontend cwd | `cloudera-ai-studio/frontend` |
| `enterprise-ai-poc` processes | None |
| `/health` | 200 |
| `/health/ready` | 200 |

## Record counts (before cleanup)

| Domain | Count |
|--------|------:|
| Projects | 109 |
| Knowledge libraries | 235 |
| Chat attachment libraries (`__cai_chat_attachments__`) | 1 |
| Documents | 266 |
| Semantic models | 441 |
| Data Source connectors | 143 |
| Prompts | 184 |
| Skills | 161 |
| Conversations | 371 |

## Classification model (applied)

| Class | Meaning | Action |
|-------|---------|--------|
| **A — SYSTEM / INTERNAL** | Required for boot, Ask Data, RAG, chat attachments, AI registry | **Preserve** |
| **B — USER/DEMO** | Intentional demo content | None retained for Golden Demo prep |
| **C — TEST / AUTOMATION** | Gates, browser smoke, M7D/M9, Phase 2, disposable models | **Delete** (metadata only) |
| **D — UNKNOWN** | Ambiguous | **Preserve** (none after conservative rules for local DB) |

### Preserved (class A)

- Global prompts with keys: `ask_data.system`, `rag.system`, `rag.insufficient_evidence`
- Workspace skills: `ask_data_analyst`, `document_qa`
- Hidden chat attachment library name: `__cai_chat_attachments__` (per preserved project)
- Default project slug: `reference_impala`
- AI Model Registry (providers, models, assignments)
- Alembic / migration metadata

### Cleanup candidates (class C) — examples

**Knowledge:** M9 bulk closure libraries, `Lib-*`, `M7D-Knowledge-*`, browser upload fixtures, regression libraries (234 user-facing libraries; attachment library excluded).

**Semantic:** Phase 1/2A/2B models, wizard/browser smoke models, publish/rollback/disposable models (441 total).

**Prompts:** Closure Prompt, M7D Iso A/B, `Proj <uuid>` overrides, `test.*` / `sit.precedence.*` globals, validation prompts (181 deletions; 3 global baseline kept).

**Skills:** Closure Skill, Draft*, M7B/M7D/exec isolation skills (159 deletions; 2 baseline kept).

**Data Sources:** Repeated Impala Dev, PG/PG2, SIT/UAT/browser connectors (143 connection records — **not** external DB tables).

**Projects:** 108 non-default isolation/test projects (automation-created slugs).

**Chat:** Conversation/message history for cleaned projects (371 conversations pre-cleanup).

## Tooling

Dry-run (default):

```bash
PYTHONPATH=backend python scripts/demo-cleanup.py --dry-run
```

Apply (local DB only):

```bash
PYTHONPATH=backend python scripts/demo-cleanup.py --apply --confirm-local-db
```
