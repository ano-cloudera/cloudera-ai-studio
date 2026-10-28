# Cloudera AI Studio — project state

**Last updated:** 2026-10-28 (MCP tab, inflight chat stream, Claude handoff)  
**Repo:** `cloudera-ai-studio` (standalone copy; source monorepo remains at `enterprise-ai-poc`)

**Stack:** Backend **8001**, Frontend **3001** — `./scripts/dev-backend.sh`, `./scripts/dev-frontend.sh`, or `./scripts/dev-stack.sh`

**Env hygiene:** [docs/deployment/LOCAL_ENV_HYGIENE.md](docs/deployment/LOCAL_ENV_HYGIENE.md)  
**Handoff (Claude):** [docs/handoff/HANDOFF_CLAUDE_2026-10-28.md](docs/handoff/HANDOFF_CLAUDE_2026-10-28.md)

## Current focus — Cloudera AI Studio AMP (deploy-ready)

**Goal:** Customer-facing **ontology-style Ask Data** accelerator — governed metrics, multi-turn memory, Knowledge `@`, **MCP `@`**, executive UX, Genie-style workspace settings. **Golden Banking** is the reference vertical + Spec Kit instance (`AMP_BANKING`), not the product boundary.

**Multi-context (workspace pin + `@`):** [AMP_MULTI_CONTEXT_POLICY.md](docs/deployment/AMP_MULTI_CONTEXT_POLICY.md) · vertical swap: [AMP_VERTICAL_SWAP_CHECKLIST.md](docs/deployment/AMP_VERTICAL_SWAP_CHECKLIST.md)

| Track | Status | Notes |
|-------|--------|--------|
| **P0 (R-01 … R-06)** | **DONE (code)** | Auto/pin semantic, session follow-up, clarification chips, governed definition panel, certified questions on publish, readiness scripts |
| **P1 (R-07 … R-11)** | **DONE (code)** | Executive preset, browse metrics API/UI, thumbs feedback, space instructions, Databricks/Ranger narrative docs |
| **Pre-AMP hardening** | **DONE** | Ask Data scope guardrail + **session stickiness** after UNSUPPORTED |
| **MCP (workspace Settings)** | **DONE (code)** | Tab **Settings → MCP**, stdio/SSE, `test-connection`, `@` picker; `verify_pre_deploy.py` |
| **Ask Data stream on navigation** | **DONE (code)** | `askDataInflightStream.ts` — chat SSE continues when leaving Ask Data tab |
| **Spec Kit** | **DONE (docs)** | `docs/testing/spec-kit/AMP_BANKING/` (spec, SIT, UAT, traceability) |
| **Manual UAT (local)** | **PASS (core)** | UAT-1–3 EN, UAT-5, UAT-7; MCP smoke via verify script |
| **Git / remote** | **OPEN** | Large **uncommitted** diff on `main` (MCP, deployment layout, settings UX) — commit when ready |
| **CAI 4-app deploy** | **OPEN** | [CAI_4_APP_DEPLOY_RUNBOOK.md](docs/deployment/CAI_4_APP_DEPLOY_RUNBOOK.md) |
| **Automated UAT / sign-off** | **OPEN** | Fill `02-uat.md`; optional live UAT scripts |
| **P2 (post-AMP)** | **DEFER** | LiteLLM gateway, `question_bank` backend removal, Default chat model UX polish |
| **P3 (roadmap)** | **OUT OF SPEC** | Multi-workspace Genie UI, full UC lineage, live Ranger demo |

**Bootstrap (target env):**

```bash
python3 scripts/demo/bootstrap_golden_banking.py --apply && python3 scripts/demo/bootstrap_golden_banking.py --validate
python3 scripts/demo/apply_accelerator_demo_profile.py
```

**Pre-deploy smoke (local):**

```bash
./scripts/dev-backend.sh start
python3 scripts/demo/verify_pre_deploy.py http://127.0.0.1:8001
```

**Handoff docs:** playbook + multi-context (above), `deployment/README.md`, `config/examples/accelerator-demo-presentation.json`

---

## Settings UX (2026-10-28)

| Area | Behavior |
|------|----------|
| **MCP** | Dedicated tab; Brave preset; Test connection + Save |
| **Starter questions** | Custom list only (legacy **question bank** removed from UI) |
| **AI Models** | Registry primary; **Default chat model** in collapsible section (runtime fallback) |

---

## Milestones (historical)

| Milestone | Status |
|-----------|--------|
| CLOUDERA_AI_STUDIO_STANDALONE_REPO | **PASS** — see `docs/migration/STANDALONE_REPO_MIGRATION_REPORT.md` |
| SOURCE_REPO_RESTORE / copy-only policy | **PASS** — `docs/migration/SOURCE_EXTRACTION_POLICY.md` |
| CONTROLLED_DEMO_ENVIRONMENT_CLEANUP | **PASS** — `docs/demo/CONTROLLED_CLEANUP_REPORT.md`, `scripts/demo-cleanup.py` |
| GOLDEN_PATH_BANKING_DEMO_PHASE1 | **PASS** — `docs/demo/GOLDEN_BANKING_DATASET.md`, evidence `testing/evidence/golden-path/PHASE1/` |
| POST_MIGRATION_STANDALONE_STABILIZATION | **PASS** — `docs/migration/POST_MIGRATION_STABILIZATION_REPORT.md` |
| KNOWLEDGE_REGATE_AND_INGESTION_RECOVERY_HARDENING | **PASS** — `docs/demo/KNOWLEDGE_RESTART_RECOVERY_REPORT.md` |
| GOLDEN_PATH_BANKING_DEMO_PHASE2_KNOWLEDGE | **PASS** — `docs/demo/GOLDEN_BANKING_KNOWLEDGE.md` |
| GOLDEN_PATH_BANKING_DEMO_PHASE3_SEMANTIC | **PASS** — gate + evidence `testing/evidence/golden-path/PHASE3-SEMANTIC/` |
| GOLDEN_PATH_BANKING_FULL_E2E_LOCAL_ACCEPTANCE | **PASS** — `docs/deployment/PRE_CAI_LOCAL_ACCEPTANCE_REPORT.md` |
| CAI_3_APP_DEPLOYMENT_READINESS | **PASS** — evidence `testing/evidence/cai-3-app-deployment-readiness/` |
| CAI_LOCAL_SIM_VALIDATION | **PASS** — `docs/deployment/CAI_LOCAL_SIM_VALIDATION_REPORT.md` |
| **AMP_BANKING_ACCELERATOR_P0_P1** | **PASS (implementation)** — pending formal UAT sign-off on deploy target |
| **MCP_WORKSPACE_SETTINGS** | **PASS (implementation)** — pending CAI runtime test (Brave / stdio) |

---

**Tests:** `make test-backend`, `make test-frontend`, `make build`  
**AMP gate:** `make amp-readiness` or `python3 scripts/demo/run_amp_accelerator_readiness.py`

**Browser smoke:** `backend/scripts/standalone_app_browser_smoke.py`

**Isolation:** `./scripts/prove-old-repo-isolation.sh`
