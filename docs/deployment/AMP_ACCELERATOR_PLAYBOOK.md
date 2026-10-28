# Cloudera AI Studio — AMP Accelerator Playbook

This playbook packages the **Cloudera AI Studio AMP** accelerator: ontology-style Ask Data (governed metrics, multi-turn memory, Knowledge RAG, executive presentation). **Golden Banking** is the in-repo **reference vertical**; other industries swap assets per [AMP_VERTICAL_SWAP_CHECKLIST.md](./AMP_VERTICAL_SWAP_CHECKLIST.md). Context routing: [AMP_MULTI_CONTEXT_POLICY.md](./AMP_MULTI_CONTEXT_POLICY.md).

## What the accelerator demonstrates

| Pillar | Demo asset |
|--------|------------|
| **Semantic layer (ontology)** | Published model `retail_banking_analytics` → PostgreSQL `banking_demo.*` |
| **Governed Ask Data** | Metric/dimension resolution, governed SQL, Impala/Postgres execution |
| **Multi-turn memory** | Same session: total amount → breakdown by channel → highest channel |
| **Knowledge RAG** | Banking policy PDFs in library |
| **Guardrails** | Unsupported intents (e.g. arbitrary Python ML) |
| **Executive UX** | Tier 1 narrative on KPIs, workspace on charts, verified-metric trust line |

## Prerequisites

- Backend + Frontend + Qdrant (local CAI sim or CAI deployment)
- LLM key (Gemini recommended for demos)
- Banking PostgreSQL with seed data (`banking_demo` schema)
- Env template: `config/examples/accelerator.env.example` → repo `.env`

## One-time demo bootstrap

```bash
export BANKING_DEMO_PG_PASSWORD="${BANKING_DEMO_PG_PASSWORD:-m1pass}"
export GOLDEN_PATH_API_BASE="${GOLDEN_PATH_API_BASE:-http://127.0.0.1:8001}"

# Platform + connector + knowledge + semantic model
python3 scripts/demo/bootstrap_golden_banking.py --apply
python3 scripts/demo/bootstrap_golden_banking.py --validate

# Publish-readiness (glossary, dimensions, metric aliases)
python3 scripts/demo/patch_banking_semantic_publish_readiness.py

# AMP demo UX preset (starters + tier1 narrative + executive mode + hero semantic pin)
python3 scripts/demo/apply_accelerator_demo_profile.py
```

The profile script pins the **hero semantic model** from `hero_semantic_model_keys` in the preset (or the sole published model). With auto-attach enabled, governed KPI questions need **no `@`**. Secondary ontologies use **`@` Semantic** or a separate deployment preset.

**P1 parity (Genie-style):**

- Browse metrics: Ask Data composer → **Browse published metrics**
- Space instructions: Settings → Ask Data → prompt key `golden_banking_executive_summary` (applied by demo preset)
- Databricks / Ranger narrative: [DATABRICKS_ONTOLOGY_PARITY.md](./DATABRICKS_ONTOLOGY_PARITY.md), [RANGER_ROW_FILTER_DEMO.md](./RANGER_ROW_FILTER_DEMO.md)

## AMP readiness gate (local)

Runs unit tests + platform checks; optional live LLM UAT.

```bash
# Fast gate (no LLM calls)
python3 scripts/demo/run_amp_accelerator_readiness.py

# Full SE rehearsal
python3 scripts/demo/run_amp_accelerator_readiness.py \
  --apply-profile \
  --patch-semantic \
  --live-uat
```

Evidence: `testing/evidence/golden-path/AMP-READINESS/readiness-gate.json`

### Spec Kit (SIT / UAT)

Formal test pack: [docs/testing/spec-kit/AMP_BANKING/](../testing/spec-kit/AMP_BANKING/00-spec.md)

- [00-spec.md](../testing/spec-kit/AMP_BANKING/00-spec.md) — requirements  
- [01-sit.md](../testing/spec-kit/AMP_BANKING/01-sit.md) — system integration tests  
- [02-uat.md](../testing/spec-kit/AMP_BANKING/02-uat.md) — user acceptance scenarios  
- [traceability.md](../testing/spec-kit/AMP_BANKING/traceability.md) — req → test mapping  

### Live UAT scripts

| Script | Purpose |
|--------|---------|
| `banking_robustness_10q.py` | 10-turn ID/EN mix, guardrails, follow-ups |
| `banking_uat_english_memory_3q.py` | English memory path (#8–#10 style) |
| `banking_ask_tier_evidence.py` | Presentation tier matrix |

## Recommended live demo script (5 minutes)

1. **Governed KPI** — “What is the total transaction amount?” (tier 1 + narrative if profile applied)
2. **Breakdown** — “Break it down by channel.” (chart + workspace)
3. **Memory** — “Which channel had the highest value?” (same session)
4. **Semantic publish** (optional 30s) — show Metrics / Glossary / publish checklist
5. **Knowledge** — **`@` attach the demo library**, ask a policy question (RAG + sources)
6. **Remove `@` library** — ask the hero KPI again (back to governed / pin)
7. **Guardrail** — “Write Python for machine learning” → unsupported

## Presentation tuning (ontology-like chat)

Workspace settings (or `config/examples/accelerator-demo-presentation.json`):

- `audience_mode`: `executive`
- `tier1_show_narrative`: `true` — short context under single-KPI answers
- `panel_auto_open`: `heuristic` — workspace when chart / many rows
- Starters: governed banking questions (applied by demo profile script)

Deployment env overrides: `ASK_DATA_AUDIENCE_MODE`, `ASK_DATA_TIER1_SHOW_NARRATIVE` in `.env`.

## CAI → AMP path

1. Complete [CAI_REAL_DEPLOYMENT_CHECKLIST.md](./CAI_REAL_DEPLOYMENT_CHECKLIST.md) on real Cloudera AI infra
2. Run bootstrap against deployed `GOLDEN_PATH_API_BASE`
3. Capture evidence under `testing/evidence/golden-path/`
4. Package from `deployment/specs/*-cai-application.md` (see `deployment/amp/README.md`)

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Wrong metric (236 customers vs amount) | Republish semantic model; restart backend; new chat session |
| “Which metric?” on follow-up | Backend includes registry session follow-up fix; same session after correct #8 |
| No Knowledge answers | Qdrant up; `@` library attached; `register_banking_knowledge.py` evidence |
| No auto semantic / wrong model | Re-run `apply_accelerator_demo_profile.py`; or Settings pin; if 2+ published models, pin is required |
| Tier 1 feels “dry” | Run `apply_accelerator_demo_profile.py` or enable tier 1 narrative in Settings |

## Related docs

- [GOLDEN_BANKING_SEMANTIC.md](../demo/GOLDEN_BANKING_SEMANTIC.md)
- [PRE_CAI_LOCAL_ACCEPTANCE_REPORT.md](./PRE_CAI_LOCAL_ACCEPTANCE_REPORT.md)
- [semantic-layer-publish-and-ask.md](../semantic-layer-publish-and-ask.md)
