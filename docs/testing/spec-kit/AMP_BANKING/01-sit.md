# SIT — Golden Banking AMP (Spec Kit)

**Environment:** Local CAI sim or staging backend + Banking PostgreSQL + LLM key  
**Entry:** `GOLDEN_PATH_API_BASE`, `BANKING_DEMO_PG_PASSWORD`

## Pre-flight

| Step | Command / check | Pass criteria |
|------|-----------------|---------------|
| SIT-0.1 | `GET /health/ready` | `core_ready=true` |
| SIT-0.2 | `bootstrap_golden_banking.py --validate` | all checks true |
| SIT-0.3 | `apply_accelerator_demo_profile.py` | HTTP 200 |

## Automated SIT (no LLM)

| Case ID | Command | Pass |
|---------|---------|------|
| SIT-1.1 | `pytest backend/tests/test_banking_demo_catalog.py` | exit 0 |
| SIT-1.2 | `pytest backend/tests/test_semantic_registry_catalog_resolver.py` | exit 0 |
| SIT-1.3 | `pytest backend/tests/test_certified_questions.py` | exit 0 |
| SIT-1.4 | `run_amp_accelerator_readiness.py` (no `--live-uat`) | gates PASS except optional bootstrap |

## API SIT (manual or script)

| Case ID | Action | Expected |
|---------|--------|----------|
| SIT-2.1 | `GET /api/v1/ask-data/settings` | `auto_attach_semantic_model=true` and non-null `default_semantic_model_id` after profile (hero pin) |
| SIT-2.2 | `POST /chat` without `context_sources`, Q: total transaction amount | `GOVERNED_SEMANTIC`, `SUM(amount)` in SQL |
| SIT-2.3 | Same session Q: Break it down by channel | SUCCESS, `GROUP BY` + channel |
| SIT-2.4 | Publish semantic model | `golden_questions.yaml` non-empty in deployment OSSIE |

Evidence: `testing/evidence/golden-path/AMP-READINESS/`
