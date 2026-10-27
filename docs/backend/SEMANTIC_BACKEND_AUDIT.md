# Semantic backend audit (pre–Semantic Layer V2)

Date: 2026-10-17  
Scope: `backend` semantic registry, validation, publish, runtime, Ask Data routing.

## 1. Architecture map

```
HTTP  /api/v1/semantic/*
  → SemanticRegistryService (CRUD, draft versions, publish, rollback, resolve_active)
  → SemanticValidationService → SemanticGovernancePipeline (structural, source, semantic, artifact)
  → OssieRuntimeAdapter (artifact generation)
  → SemanticRuntimeService (stage, validate deployment, activate, rollback)
  → SemanticRuntimeLoader (in-memory bundle swap, legacy fallback)

Ask Data /chat
  → ChatService.normalize_request → apply_context_sources (Knowledge/RAG, attachments)
  → LangGraph workflow + semantic registry / OSSIE runtime loader
  → AskDataDatasourceRouter + ConnectorDatasourceExecutor (connector-backed SQL)
```

## 2. Canonical services

| Concern | Canonical implementation |
|--------|---------------------------|
| Model CRUD | `SemanticRegistryService` |
| Draft content | Version-scoped rows (`Semantic*Row` + `semantic_version_id`) |
| Validate | `SemanticGovernancePipeline` via `SemanticValidationService` |
| Registry publish | `SemanticRegistryService.publish_version` (validates, artifact, `_activate_version`) |
| Runtime stage/activate | `SemanticRuntimeService.stage_version` / `activate_deployment` |
| Active runtime read | `SemanticRuntimeLoader.get_bundle()` |
| OSSIE artifact | `OssieRuntimeAdapter.generate_artifact` |
| Connector metadata | `ConnectorMetadataResolver` / connector discovery |
| Project scope | `default_project_context` + row `workspace_id` / `project_id` checks |

Legacy/overlap: separate manual `/validate`, `/publish`, `/runtime/.../activate` API steps (V2 adds orchestration).

## 3. State model

**Registry version (`SemanticVersionRow.status`):** `DRAFT` → publish → `ACTIVE`; prior active → `ARCHIVED`.  
**Readiness:** `activation_readiness` (`NOT_READY`, `READY`, `READY_WITH_WARNINGS`).  
**Runtime deployment:** `STAGED` → `VALIDATING` → `READY` → `ACTIVATING` → `ACTIVE` / `FAILED`.

Valid transitions enforced in service methods; invalid publish/activate returns `SemanticRegistryError` / `SemanticRuntimeError`.

## 4. Registry vs runtime separation

- Registry publish marks version `ACTIVE` and generates OSSIE artifact metadata on the version row.
- Runtime activation is a **separate** deployment row under `SemanticRuntimeDeploymentRow` + `SemanticRuntimeStateRow.active_deployment_id`.
- `activate_deployment` rolls back in-memory bundle swap on smoke/load failure; failed deployment → `FAILED`, previous bundle restored when possible.

**Risk (pre-V2):** UI could show registry active while runtime still on prior deployment if user skips activate.

## 5. Failure boundaries

- DB mutations flush per service call; no single cross-store transaction (Postgres + filesystem artifacts + in-memory loader).
- Activation failure: deployment `FAILED`, loader reverts to previous bundle when smoke fails after swap.
- Publish blocked when validation `NOT_READY`.

## 6. Project isolation

Model/version/entity/metric/dimension/relationship/term rows carry `workspace_id` / `project_id` via model ownership; services call `get_model` / `get_version` before mutations. Connector references validated via `ConnectorRegistryService.get_connector(..., workspace_id, project_id)`.

## 7. Raw table Ask path (Phase 1)

- `StructuredContextResolver` + stable `tr:…` table IDs (`app/ask_data/table_context_id.py`).
- `AskDataDatasourceRouter.resolve_raw_table` scopes connector execution (`allowed_physical_tables`).
- `ChatService.run/stream` applies structured precedence before v3/OSSIE routing; explicit context forces OSSIE path.
- SQL governance: existing validator + `raw_table_policy` column allow-list (SELECT/WITH-only unchanged).

## 8. Clarification path (Phase 1)

- Registry/domain clarifications unchanged for governed metrics.
- Multi-source table ambiguity: `status=clarification_required`, `reason=AMBIGUOUS_DATA_SOURCE`, structured `options[]` on `AskDataResponse.clarification`.
- Explicit broken `@metric` / `@table`: `ERROR` with `explicit_context_unavailable` caveat (no silent legacy fallback).

### Ask Data routing precedence (implemented)

1. `normalize_request` → family mix guard (`apply_context_sources`)
2. `resolve_structured_ask` (explicit `@` or auto single-table)
3. Clarification short-circuit or explicit context error
4. Optional runtime bundle swap for explicit semantic model/metric
5. `_route_for_question` (OSSIE/registry resolve) when no structured resolution
6. v3 agent only when no explicit structured context and routing allows
7. LangGraph workflow (governed compile or raw-table sql_fallback planner)

## 9. AI suggestions

No persisted suggestion store pre-V2. V2 adds `POST /api/v1/semantic/suggestions` (deterministic heuristics; LLM enrichment optional later).

## 10. V2 additions (this branch)

| Component | Path |
|-----------|------|
| Publish orchestration | `app/services/semantic_publish_orchestration.py` |
| API | `POST /api/v1/semantic/models/{id}/publish-to-ask-data` |
| Suggestions | `app/services/semantic_suggestions_service.py` |
| @ picker options | `GET /api/v1/chat/context-options` |
| Context types | Extended `ChatContextSource` in `app/core/models.py` |

## 11. Known technical debt

- Multi-step manual validate/publish/activate UX (orchestration API added, FE not fully migrated).
- Raw table Ask without semantic model — resolver not in LangGraph yet.
- Context picker DATA group currently lists connector-mapped **entities**, not full connector catalog browse.
- Optimistic locking on concurrent draft edits not implemented (`SEMANTIC_VERSION_CONFLICT` TBD).
- Full SEM-BE-001…025 robustness suite not complete.

## 12. Components reused (do not duplicate)

`SemanticGovernancePipeline`, `SemanticRegistryService.publish_version`, `SemanticRuntimeService.stage_version/activate_deployment`, `SemanticRuntimeLoader`, `AskDataDatasourceRouter`, `ConnectorMetadataResolver`.
