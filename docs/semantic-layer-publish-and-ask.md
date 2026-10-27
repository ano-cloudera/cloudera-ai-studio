# Semantic layer: register → publish → Ask Data @ context

This is the supported path from database tables to governed chat.

## 1. Author in Semantic Layer (platform DB)

1. **Connect** a data connector (warehouse / lakehouse).
2. **Import tables** into a draft semantic version (entities + dimension columns).
3. Define **metrics**, **relationships**, and **glossary terms** (optional but recommended).
4. Run **Validate** on the draft version (structural, source, semantic, artifact checks).

Authoring state lives in PostgreSQL (`semantic_models`, `semantic_versions`, metrics, dimensions, terms). It is not yet used by Ask Data until publish.

## 2. Publish to Ask Data (NFS runtime bundle)

1. Use **Publish to Ask Data** on the model (orchestration: validate → registry ACTIVE → stage → activate).
2. The runtime writer creates an immutable folder:

   `{SEMANTIC_RUNTIME_STORAGE_ROOT}/{workspace_id}/{project_id}/{model_key}/deployments/{deployment_id}/`

   - `ossie/tempo_core.ossie.yaml` — entities, dimensions (fields), metrics  
   - `ossie/tempo_governance.yaml` — glossary snapshot, `runtime_extensions` (profile + phrase map from terms)  
   - `manifest.json` — checksum and version metadata  

3. The model’s **active deployment** must be `ACTIVE` before `@Semantic` works.

Set `SEMANTIC_RUNTIME_STORAGE_ROOT` (or `CAI_DATA_DIR`) so this tree lives on shared storage (e.g. Cloudera AI NFS) in production.

## 3. Ask Data with @ context

In Ask Data, type `@` and pick one structured context (only **one** per message):

| @ chip | Meaning |
|--------|---------|
| `@Semantic: …` | Whole published model — metric resolver uses all OSSIE metrics/dimensions |
| `@Metric: …` | Single governed metric |
| `@Entity: …` | Single entity (dataset) scope |
| `@Term: …` | Glossary term — prefers linked metric; otherwise falls back to model scope |
| `@Table: …` | Raw table (non-semantic) path |

**Requirements**

- Model must be **published** (active version + runtime deployment).
- Backend loads the **ACTIVE** deployment OSSIE bundle from NFS, not the draft DB rows directly.

## 4. Glossary and runtime extensions

- **Terms** edited in Semantic Layer are copied into `tempo_governance.yaml` → `glossary` on publish.
- Terms with **related dimension keys** become breakdown phrase hints (`runtime_extensions.breakdown.phrase_map`).
- Optional **code profiles** under `backend/app/semantic/runtime_extensions/profiles/` (e.g. `banking_demo`) attach when dataset sources match; publish stores `profile: <name>` in governance instead of duplicating the whole profile.

At runtime, Ask Data merges governance glossary + extensions when loading the OSSIE registry.

## 5. Troubleshooting

| Symptom | Check |
|---------|--------|
| “Not published to Ask Data” | Publish + activation; `active_version_id` on model |
| @Semantic works but wrong breakdown | Glossary term → dimension links; republish after term edits |
| Dev vs prod differ | Same deployment checksum? NFS path shared? |

**Rule of thumb:** edit in DB → validate → publish → `@Semantic` in UI. Skipping publish means Ask Data still sees the previous NFS snapshot (or nothing).
