# Prompt Management — Design (M3A)

## Goals

Reusable, versioned prompts for the accelerator with **draft / publish / rollback**, scoped overrides, and **legacy file fallback** during migration.

## Hierarchy

```text
Global (scope=global, no workspace/project ids)
    ↓
Workspace (scope=workspace, workspace_id set)
    ↓
Project (scope=project, workspace_id + project_id)
    ↓
Skill (M3B — future)
    ↓
Session context (orchestrator-injected, not stored as prompt versions)
    ↓
User message
```

## Data model

Tables: `prompts`, `prompt_versions` (Postgres platform DB).

| prompts | |
|---------|---|
| id | UUID PK |
| workspace_id | nullable |
| project_id | nullable |
| name, key, scope | scope ∈ `global`, `workspace`, `project` |
| description | optional |
| active_version_id | FK → prompt_versions |
| created_at, updated_at | |

| prompt_versions | |
|-----------------|---|
| id | UUID PK |
| prompt_id | FK |
| version_number | monotonic per prompt |
| content | text |
| status | `DRAFT`, `ACTIVE`, `ARCHIVED` |
| created_by | optional |
| created_at | |

Only one **ACTIVE** version per prompt.

## Initial keys

| Key | File fallback |
|-----|----------------|
| `ask_data.system` | `prompts/global_system.md` |
| `rag.system` | `prompts/rag_system.txt` (or `RAG_SYSTEM_PROMPT_PATH`) |
| `rag.insufficient_evidence` | built-in insufficient message constant |

## Sources

- `DatabasePromptSource` — active published content only  
- `FilePromptSource` — legacy disk prompts  

`PromptResolver` prefers DB when Postgres platform store is configured and a session is available; otherwise files.

## Security

- Prompt APIs are admin/configuration surfaces (not exposed on chat).
- Avoid logging full prompt bodies in application logs or usage telemetry.

## Migration

`scripts/seed_prompts.py` imports file content into **draft** global rows (idempotent). Disk files are **not** deleted. Publish when ready to override runtime.

## Out of scope (M3A)

Skills, semantic layer manager, hybrid router, RBAC, approval workflows.
