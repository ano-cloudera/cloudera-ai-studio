# Semantic Layer V2 (in progress)

## Product model

- **Raw data → flexibility:** Ask Data works with connected tables via `@` context (target).
- **Semantic layer → trust:** Published models/metrics provide governed answers.

## UX (partial)

- Primary tabs: Overview, **Data Models**, Metrics, Dimensions, Relationships, Glossary.
- **Advanced ▾:** Model health (validation), Version history, Deployment details (runtime).
- Publish CTA target: **Publish to Ask Data** (API ready; UI still migrating off validate/publish/activate steps).

## @ context types

| Type | Chip example |
|------|----------------|
| `table` | `@Table: public.sales` |
| `semantic_model` | `@Semantic: Commercial Sales` |
| `semantic_entity` | `@Entity: Customer` |
| `semantic_metric` | `@Metric: Total Sales` |
| `knowledge_library` | (unchanged) |

Options loaded from `GET /api/v1/chat/context-options` (grouped DATA / SEMANTIC / KNOWLEDGE).

## Publish lifecycle (backend)

`POST /api/v1/semantic/models/{model_id}/publish-to-ask-data`

Runs validate → registry publish → runtime stage → activate. Returns `needs_attention` (422) or `activation_failed` (502) with structured detail.

## Phase 1 — Structured Ask Data (backend)

### Context types (stable IDs)

| Type | ID source | Runtime mode |
|------|-----------|--------------|
| `table` | `tr:{connector_id}:{catalog}:{schema}:{table}` (legacy: semantic entity UUID) | `RAW_TABLE` |
| `semantic_metric` | `SemanticMetricRow.id` | `GOVERNED_SEMANTIC` |
| `semantic_model` | `SemanticModelRow.id` | `GOVERNED_SEMANTIC` |
| `semantic_entity` | `SemanticEntityRow.id` (connector-linked → raw table path) | `RAW_TABLE` or governed model |
| `knowledge_library` / `uploaded_file` | unchanged | RAG |

### Precedence

1. Explicit `@` structured context (never silent legacy fallback on failure)
2. Published semantic runtime resolution (when no explicit context)
3. Single high-confidence connector table match (auto)
4. `clarification_required` + `AMBIGUOUS_DATA_SOURCE` when multiple tables match

Explicit semantic metric/model loads the model’s active runtime bundle before resolve/compile.

### API fields

- `AskDataResponse.context_mode`: `RAW_TABLE` | `GOVERNED_SEMANTIC`
- `AskDataResponse.clarification`: `{ reason, message, options[] }` with `status=clarification_required`

Picker: `GET /api/v1/chat/context-options` — DATA lists connector metadata tables (not only semantic entities).

## Phase 2 — Authoring UX (in progress)

### Navigation

- Primary tabs: Overview, Data Models, Metrics, Dimensions, Relationships, Glossary.
- **Advanced ▾:** Model health, Version history, Deployment details (validation / versions / runtime tabs).

### Overview

- Business summary cards (counts), readiness line, **Publish to Ask Data** CTA.
- Registry/runtime internals moved off the primary overview (still under Advanced).

### Save / Cancel

- Custom **Unsaved changes** modal for semantic tab switches when `dirty` is set (Keep editing / Discard / Save and continue).
- Editors still migrating to explicit **Save** + **Cancel** on every drawer; `Save and continue` requires an active editor save handler.

### Publish

- **Publish to Ask Data** calls `POST /api/v1/semantic/models/{id}/publish-to-ask-data` (orchestrated validate → publish → stage → activate).
- Success and `needs_attention` issue panels on the page toolbar.

### Ask Data integration (Phase 2 polish)

- **Raw data** / **Governed semantic** badges via `ContextModeBadge`.
- Structured clarification choices attach `contextSource` and re-submit the prior user question.

### Backend (Phase 2)

- `GET /models/{id}/overview` — counts, state, readiness.
- Paginated list query on entities/metrics (`search`, `sort`, `order`, `page`, `page_size`) with sort whitelist.

### Tests & gates

- Vitest: `semanticLayerPhase2.test.tsx`, updated `SemanticLayerPage.test.tsx`.
- Live API: `backend/scripts/sem_p2_live_gate.py` (overview + paginated lists + suggestions + model health).
- Phase 1 live gate unchanged: `sem_p1_live_gate.py`.

## Phase 2A Advanced UX (nav-only)

- **Single Advanced control** in the primary tab row (after Glossary). Toolbar keeps model selector, status, and **Publish to Ask Data** only.
- **Advanced menu:** Model health, Version history, Deployment details, Preview semantic artifact. No duplicate Validate / Publish version entries.
- **Overview:** five summary cards on one row at `xl` (`semantic-overview-summary`); no duplicate footer links to admin views.

## Phase 2A authoring standard (closure)

- **Tables:** `SemanticAuthoringTableShell` + paginated API lists (`search`, `sort`, `order`, `page`, `page_size`). Default sort `modified` desc.
- **Selection:** Hidden checkbox column until **Select** is pressed. Page select-all, selected count, **Delete selected** (bulk-delete API), **Cancel** clears selection and exits mode. Selection clears on search/page/sort changes.
- **Bulk delete:** `POST /api/v1/semantic/versions/{version_id}/{entities|metrics|dimensions|relationships|terms}/bulk-delete` with `{ "ids": ["…"] }` — per-item deleted/failed, project-scoped, max batch from `bulk_delete_max_items`.
- **Metric validation:** Local draft checks in `metricValidation.ts`; authoritative `POST …/metrics/validate` before save. Field-level messages for name, definition, data model, expression (missing column, non-numeric SUM, etc.).
- **Glossary mappings:** Terms store `related_entity_keys`, `related_metric_keys`, `related_dimension_keys` (stable keys). Editor uses searchable grouped multi-select (`GlossaryRelatedObjectPicker`); backend validates keys exist on the draft version.
- **Loading hang (fixed):** Initial page load no longer re-triggers `refreshModels` when `modelId` is set (stable `useCallback` deps). Authoring selection clear effect depends on `selection.clear` only, avoiding a render loop that could freeze the UI.

## Phase 2B workflow closure

- **Create semantic model wizard:** Step 1 model name/description; Step 2 connector-grouped table multi-select with search; Step 3 AI suggestions grouped by type with Accept / Edit / Reject (and bulk actions). Finish persists accepted objects only via `POST /api/v1/semantic/models/{model_id}/suggestions/accept` (canonical registry creates). Completion summary stays **Draft** — no auto-publish.
- **Suggestion contract:** Ephemeral suggestions until accepted; rejected rows are not stored; edited payloads persist only on accept; duplicate keys surface as conflicts (no silent overwrite).
- **Dirty-state UX:** Custom **Unsaved changes** modal (Keep editing / Discard / Save and continue) blocks tab, model, Advanced, and drawer navigation when an editor is dirty. `beforeunload` only for browser tab close. Normal flow does not use `window.confirm`.
- **Publish to Ask Data:** Primary CTA calls `POST /api/v1/semantic/models/{model_id}/publish-to-ask-data` with lightweight progress copy. Success shows version + active state; `needs_attention` shows grouped issue panel with deep-link; activation failure does not claim active runtime.
- **Post-publish editing:** Published version remains active for Ask Data; saved edits after publish return the model to **Draft** until the next publish.
- **Rollback:** Version history uses product confirmation modal (not native confirm).
- **Header UX:** One title + caption; searchable semantic model combobox (name/key filter); Import OSSIE / Create semantic model as white secondary buttons; Publish remains primary.

### Phase 2B gates

- Vitest: `semanticLayerPhase2B.test.tsx` (SEM-2B smoke subset) + full suite.
- Live API: `backend/scripts/sem_p2b_live_gate.py` (accept route, publish, P1/P2/P2A regression slices).
- Browser: `backend/scripts/sem_p2b_browser_smoke.py` — evidence under `testing/evidence/post-uat/SEMANTIC-LAYER-V2/PHASE2B/`.

## Known limitations (Phase 2C)

- Full SEM-2B-001–041 Vitest matrix not yet exhaustively enumerated in one file (core flows covered; expand before Phase 2C evidence closure).
