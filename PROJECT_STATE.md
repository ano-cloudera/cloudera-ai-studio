# Cloudera AI Studio — project state

**Last updated:** 2026-10-27  
**Repo:** `cloudera-ai-studio` (standalone copy; source monorepo remains at `enterprise-ai-poc`)

**Stack:** Backend **8001**, Frontend **3001** — `./scripts/dev-backend.sh`, `./scripts/dev-frontend.sh`, or `./scripts/dev-stack.sh`

## Current focus — AMP Golden Banking (deploy-ready)

**Goal:** Customer-facing **ontology-style Ask Data** demo (Golden Banking) — governed metrics, multi-turn EN memory, executive UX, Genie-style settings.

| Track | Status | Notes |
|-------|--------|--------|
| **P0 (R-01 … R-06)** | **DONE (code)** | Auto/pin semantic, session follow-up, clarification chips, governed definition panel, certified questions on publish, readiness scripts |
| **P1 (R-07 … R-11)** | **DONE (code)** | Executive preset, browse metrics API/UI, thumbs feedback, space instructions, Databricks/Ranger narrative docs |
| **Pre-AMP hardening** | **DONE** | Ask Data scope guardrail + **session stickiness** after UNSUPPORTED (blocks coaxing → metric chips) |
| **Spec Kit** | **DONE (docs)** | `docs/testing/spec-kit/AMP_BANKING/` (spec, SIT, UAT, traceability) |
| **Manual UAT (local)** | **PASS (core)** | UAT-1–3 EN (no `@`), UAT-5 governed definition, UAT-7 ML guardrail; evidence = screenshots / chat replay |
| **Automated UAT / sign-off** | **OPEN** | Optional: `banking_uat_english_memory_3q.py`, `run_amp_accelerator_readiness.py --live-uat`, fill `02-uat.md` sign-off table |
| **P2 (post-AMP)** | **DEFER** | LiteLLM gateway wiring, broader guardrails, full UAT-6–8 routine, env deploy checklist |
| **P3 (roadmap)** | **OUT OF SPEC** | Multi-workspace Genie UI, full UC lineage, live Ranger demo, CAI artifact packaging |

**Bootstrap (target env):**

```bash
python3 scripts/demo/bootstrap_golden_banking.py --apply && python3 scripts/demo/bootstrap_golden_banking.py --validate
python3 scripts/demo/apply_accelerator_demo_profile.py
```

**Handoff docs:** `docs/deployment/AMP_ACCELERATOR_PLAYBOOK.md`, `deployment/amp/README.md`, `config/examples/accelerator-demo-presentation.json`

---

## Milestones (historical)

| Milestone | Status |
|-----------|--------|
| CLOUDERA_AI_STUDIO_STANDALONE_REPO | **PASS** — see `docs/migration/STANDALONE_REPO_MIGRATION_REPORT.md` |
| SOURCE_REPO_RESTORE / copy-only policy | **PASS** — `docs/migration/SOURCE_EXTRACTION_POLICY.md` |
| CONTROLLED_DEMO_ENVIRONMENT_CLEANUP | **PASS** — `docs/demo/CONTROLLED_CLEANUP_REPORT.md`, `scripts/demo-cleanup.py` |
| GOLDEN_PATH_BANKING_DEMO_PHASE1 | **PASS** — `docs/demo/GOLDEN_BANKING_DATASET.md`, evidence `testing/evidence/golden-path/PHASE1/` |
| POST_MIGRATION_STANDALONE_STABILIZATION | **PASS** — `docs/migration/POST_MIGRATION_STABILIZATION_REPORT.md` |
| KNOWLEDGE_REGATE_AND_INGESTION_RECOVERY_HARDENING | **PASS** — `docs/demo/KNOWLEDGE_RESTART_RECOVERY_REPORT.md`, `docs/architecture/KNOWLEDGE_INGESTION_LIFECYCLE.md` |
| GOLDEN_PATH_BANKING_DEMO_PHASE2_KNOWLEDGE | **PASS** — `docs/demo/GOLDEN_BANKING_KNOWLEDGE.md` |
| GOLDEN_PATH_BANKING_DEMO_PHASE3_SEMANTIC | **PASS** — `docs/demo/GOLDEN_BANKING_SEMANTIC.md`, gate `scripts/demo/golden_path_banking_phase3_semantic_gate.py`, evidence `testing/evidence/golden-path/PHASE3-SEMANTIC/` |
| PHASE3_SEMANTIC_FINAL_UI_AND_CHAT_CLOSURE | **PASS** — `docs/demo/PHASE3_SEMANTIC_CLOSURE_REPORT.md`, gate `scripts/demo/golden_path_banking_phase3_closure_gate.py`, browser `PHASE3-SEMANTIC/browser/` |
| GOLDEN_PATH_BANKING_FULL_E2E_LOCAL_ACCEPTANCE | **PASS** — `docs/demo/GOLDEN_BANKING_FULL_E2E.md`, `docs/deployment/PRE_CAI_LOCAL_ACCEPTANCE_REPORT.md`, gate `scripts/demo/golden_path_banking_full_e2e_gate.py`, evidence `testing/evidence/golden-path/FULL-E2E/` |
| CAI_3_APP_DEPLOYMENT_READINESS | **PASS** — `docs/deployment/CAI_3_APP_DEPLOYMENT_READINESS.md`, gate `scripts/cai/cai_3_app_deployment_readiness_gate.py`, evidence `testing/evidence/cai-3-app-deployment-readiness/` |
| CAI_3_APP_PERSISTENCE_ARCHITECTURE_AUDIT | **PASS** — `docs/architecture/CAI_3_APP_PERSISTENCE_ARCHITECTURE_AUDIT.md`, `docs/architecture/CAI_DEPLOYMENT_ENV_CONTRACT.md` |
| METADATA_001_SQLITE_PORTABILITY_LOCAL_ACCEPTANCE | **PASS** — `docs/architecture/METADATA_001_SQLITE_PORTABILITY.md`, `docs/deployment/LOCAL_CAI_SIMULATION.md`, evidence `testing/evidence/metadata-001/` |
| CAI_LOCAL_SIM_VALIDATION | **PASS** — `docs/deployment/CAI_LOCAL_SIM_VALIDATION_REPORT.md`, evidence `testing/evidence/cai-local-sim-validation/` |
| **AMP_BANKING_ACCELERATOR_P0_P1** | **PASS (implementation)** — Spec Kit + playbook; **pending:** formal automated UAT evidence on deploy target |

---

**Tests:** `make test-backend` (deterministic), `make test-frontend`, `make build`  
**AMP gate (fast):** `make amp-readiness` or `python3 scripts/demo/run_amp_accelerator_readiness.py`

**Browser smoke:** `backend/scripts/standalone_app_browser_smoke.py` (evidence under `testing/evidence/standalone/BROWSER_SMOKE/`)

**Isolation:** `./scripts/prove-old-repo-isolation.sh` (non-destructive; does not move source repo)
