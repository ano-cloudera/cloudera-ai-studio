# Semantic Registry — Design (S1)

## Source of truth

| Layer | Role |
|-------|------|
| **PostgreSQL Semantic Registry** | Canonical authoring, versioning, validation, publish/rollback |
| **OSSIE YAML on disk** | Current **runtime** artifact (unchanged in S1) |
| **Generated OSSIE YAML** | Future runtime artifact produced from **ACTIVE** registry version |

Frontend must not edit raw OSSIE YAML. Management flows through `/api/v1/semantic/*`.

## Hierarchy

```text
Workspace → Project → SemanticModel → SemanticVersion
                                          ├── Entities
                                          ├── Metrics
                                          ├── Dimensions
                                          ├── Relationships
                                          └── Terms (glossary)
```

## Version lifecycle

1. Create model → initial **DRAFT** version  
2. Edit objects (DRAFT only)  
3. **Validate** → structured errors/warnings  
4. **Publish** → prior ACTIVE archived; optional OSSIE artifact preview written under `var/semantic-artifacts/`  
5. **Rollback** → re-activate archived version  

Editing ACTIVE: **clone** to new DRAFT, then edit.

## Services

- `SemanticRegistryService` — CRUD, lifecycle, resolution, artifact preview orchestration  
- `SemanticGovernancePipeline` (S3) — structural, source, semantic, artifact, readiness validation; persisted runs  
- `SemanticSourceValidator` — Impala (+ duckdb dev path) and Trino adapters (`metadata_only` / `safe_query`)  
- `SemanticDiffService` — version diff + breaking-change classification  
- `OssieImporter` — read-only bootstrap from existing `tempo_core.ossie.yaml`  
- `OssieRuntimeAdapter` — deterministic YAML preview from normalized rows  

## Validation (S3)

Levels: **STRUCTURE → SOURCE → METRIC/DIMENSION/RELATIONSHIP/GLOSSARY → ARTIFACT → RUNTIME_READINESS**

Readiness: `NOT_READY` (any ERROR) · `READY_WITH_WARNINGS` · `READY` (activation-eligible for S4).

Publish runs **full** validation; ERROR blocks publish. Warnings require explicit FE confirmation.

Migration: `s3_semantic_gov_001` (`semantic_validation_runs`, `semantic_validation_issues`, `semantic_test_cases`, version readiness columns).

## Runtime (S1)

Ask Data continues to use **`SemanticContextService` + on-disk OSSIE** via `resolve_ossie_project_dir`. Registry is **not** wired into query planning in S1.

## Runtime activation (S4)

Tables: `semantic_runtime_deployments`, `semantic_runtime_state`, `semantic_runtime_events`.

ACTIVE registry version → stage artifact → pre-activation validate/smoke → activate pointer → `SemanticRuntimeLoader` → Ask Data (legacy OSSIE fallback when no deployment).

See [SEMANTIC_RUNTIME_ACTIVATION.md](./SEMANTIC_RUNTIME_ACTIVATION.md).

## Connector binding (C4)

`semantic_entities.connection_id` → `connectors.id` (nullable, RESTRICT on delete).

- `SemanticEntityImportService` — import from C2 table metadata on DRAFT versions only
- `ConnectorMetadataResolver` — source validation via connector when `connection_id` is set
- Legacy entities (`connection_id` null) unchanged

See [CONNECTOR_SEMANTIC_INTEGRATION.md](../architecture/CONNECTOR_SEMANTIC_INTEGRATION.md).
