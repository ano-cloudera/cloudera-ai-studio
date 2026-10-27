# Semantic Runtime Activation (S4)

## Overview

S4 separates **registry active** from **runtime active**:

| State | Meaning |
|-------|---------|
| Registry ACTIVE | Published semantic version in PostgreSQL (`semantic_models.active_version_id`) |
| Runtime ACTIVE | Deployment whose OSSIE artifact is loaded by Ask Data (`semantic_runtime_state.active_deployment_id`) |

Publish does **not** activate runtime. Activation is an explicit, validated lifecycle.

## Lifecycle

```
DRAFT → validate (S3) → publish registry (ACTIVE)
  → stage deployment (artifact write)
  → pre-activation validate + smoke
  → optional dry-run (?dry_run=true)
  → atomic activate (DB pointer + in-memory context swap)
  → post-activation health
  → ACTIVE deployment
```

On health failure after swap: in-memory context rolls back to previous bundle; DB pointer is not updated.

## Artifacts

Immutable versioned storage under `SEMANTIC_RUNTIME_STORAGE_ROOT`:

```
{workspace_id}/{project_id}/{model_key}/deployments/{deployment_id}/
  ossie/tempo_core.ossie.yaml
  ossie/tempo_governance.yaml (copied from legacy when present)
  manifest.json
```

Logical URI exposed to clients: `semantic-runtime://{model_key}/deployments/{deployment_id}`.

## Runtime loader

`SemanticRuntimeLoader` (singleton):

1. On startup / activation: load `semantic_runtime_state` → ACTIVE deployment artifact
2. If missing or load fails: try `previous_deployment_id`, then **legacy OSSIE** via `resolve_ossie_project_dir`

`ChatService` syncs workflow semantic context from the loader each Ask Data request (consistent per turn).

## APIs

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/semantic/runtime/status` | Registry vs runtime versions, health |
| GET | `/api/v1/semantic/runtime/deployments` | History |
| GET | `/api/v1/semantic/runtime/deployments/{id}` | Detail + events |
| POST | `/api/v1/semantic/versions/{id}/runtime/stage` | Generate + stage artifact |
| POST | `/api/v1/semantic/runtime/deployments/{id}/validate` | Pre-activation validation |
| POST | `/api/v1/semantic/runtime/deployments/{id}/smoke` | Smoke test |
| POST | `/api/v1/semantic/runtime/deployments/{id}/activate` | Activate (`?dry_run=true` supported) |
| POST | `/api/v1/semantic/runtime/deployments/{id}/rollback` | Manual rollback to prior ACTIVE/SUPERSEDED deployment |

## Concurrency

Activation acquires a row lock on `semantic_runtime_state` and rejects concurrent `ACTIVATING` deployments (409).

## CAI / NFS

Set `SEMANTIC_RUNTIME_STORAGE_ROOT` to a durable NFS-backed path in CAI; local dev may use a repo-relative directory.

## UI

Semantic Layer overview shows separate Registry and Runtime cards, **Validate for activation**, **Activate runtime**, and a **Runtime** history tab with rollback.
