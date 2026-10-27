# Phase C — Agreed architecture (TEMPO Ask Data v2)

North star: **correct, intelligible answers** inside **governed** guardrails — not free SQL.

## Principles

1. Grounded numbers (Impala + published views/metrics).
2. Clarify before guess (FE chips + OSSIE ambiguities).
3. Single semantic catalog (OSSIE); tempo_agent_v3 sidecar **temporary** for parity only.
4. Judge may **replan and re-execute** SQL, not only rewrite narrative.
5. Conversational / capability questions skip Impala.

## Workstreams

| ID | Item | Status |
|----|------|--------|
| C1 | Judge `retry_plan` → `plan_query` → validate → execute → analyze | Done |
| C2 | Rank Top-N DC stock (`sat_dc_stock_quantity` @ `dcname`) | Done |
| C3 | OSSIE stream agent trace (labels like v3) | Done |
| C4 | OSSIE-only stack script (`scripts/run-local-stack-ossie-only.sh`) | Done |
| C5 | Clarify UX + B3 regression (10 management questions) | Partial (dry all→OSSIE; live Q02/Q03/Q08 + DC smoke OK) |
| C6 | Domain business graph (YAML) → inquiry brief + cabang + B3 governed_intents | Done (`knowledge/tempo_domain_graph.yaml`, 7/10 dry resolved) |
| C7 | PuppyGraph infra (optional entity scope) | Stub (`puppygraph_schema_stub.yaml`, client off by default) |
| C8 | Multi-turn follow-up UAT (5×2 per domain, Gemini judge) | **50/50** scenarios (6 Oct 2026 merged `uat_domain_5x5_followup_merged_latest.json`); promo-fu-05 fix: `program_status` catalog + uplift follow-up routing |

## Routing target

- `conversational` → greeting prompt only.
- `analytic` + resolved → OSSIE governed path (+ judge).
- `analytic` + ambiguous → CLARIFICATION (not ERROR).
- v3 optional until C4 passes B3 without sidecar.

## Owner checklist

- [x] Restart backend after C1/C2 changes (`run-local-stack-ossie-only.sh`).
- [x] Smoke: DC Top 10 penumpukan stok — SUCCESS, 10 rows, ~37s, route `ossie`.
- [x] Set `ASK_DATA_ROUTING=auto`, `LOCAL_AGENT_PRIMARY=0`, empty `LOCAL_AGENT_BASE_URL` for OSSIE demo.
- [ ] Full live B3 (10/10) + golden YAML pass/fail.
