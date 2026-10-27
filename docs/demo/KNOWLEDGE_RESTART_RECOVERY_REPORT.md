# Knowledge restart recovery — validation report

**Milestone:** `KNOWLEDGE_REGATE_AND_INGESTION_RECOVERY_HARDENING`  
**Date:** 2026-10-18

## Stage A — Phase 2 re-gate

| Check | Result |
|-------|--------|
| `golden_path_banking_phase2_knowledge_gate.py` | **GOLDEN_PATH_BANKING_DEMO_PHASE2_KNOWLEDGE_PASS** |
| Phase 1 regression | PASS (via gate) |

## Pre-fix storage audit

| Finding | Action |
|---------|--------|
| `backend/backend/runtime/document_storage` (52K) | 13 blobs copied to canonical root via `repair_pre_fix_storage_blobs.py` |
| Golden Banking PDFs | Now present under `backend/runtime/document_storage` |
| Orphan tree | Removed after repair (`orphan-only after repair: 0`) |

Evidence: `testing/evidence/knowledge-ingestion-recovery/orphan-storage-repair.json`

## Stage B — Restart reproduction

Live script: `scripts/demo/knowledge_ingestion_restart_evidence.py`

- Upload PDF → backend **stop** during ingestion → **start**
- Startup recovery requeued document
- Final **READY**, `chunk_count=2`

Evidence: `testing/evidence/knowledge-ingestion-recovery/restart-recovery-live.json`

## Automated tests

`backend/tests/test_knowledge_ingestion_recovery.py` (integration):

- PROCESSING → recovery requeue
- READY / FAILED / chat attachment excluded
- End-to-end recovery + no duplicate chunks on second scan
- Missing blob → FAILED

Run: `cd backend && GOLDEN_BANKING_RUN_INTEGRATION=1 PYTHONPATH=. pytest -m integration tests/test_knowledge_ingestion_recovery.py`

## Regression

- `make test-backend`: 428 passed (+ recovery tests run under `-m integration`)
- Frontend Vitest / build: PASS (see milestone gate run)
- Browser smoke: PASS
