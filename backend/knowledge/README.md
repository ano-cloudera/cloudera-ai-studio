# TEMPO knowledge (backend)

## `tempo_domain_graph.yaml`

In-process **business context graph** (not a graph database). Used when `BUSINESS_GRAPH_ENABLED=true`.

- **domains / entities / journeys** — cross-domain narrative and journey view references (A–D).
- **disambiguation.cabang** — Sell-In `sales_office` vs B2B `branch`.
- **partner_scope.alfamart** — B2B Sell-Out + Stock SAT (partition SAT) = Alfamart partner network in Q4 PoC; **not** a SQL `branch='Alfamart'` filter (see OSSIE dataset instructions).
- **governed_intents** — deterministic OSSIE metric selection before generic `sales_stage` / stock ambiguity (B3 Q01, Q05, Q10, DC penumpukan).

### Routing guardrails (resolver order in `semantic/context.py`)

1. **Bill-to-PO** → `material_fill_rate` (DO÷PO), before generic "penagihan" sell-in.
2. **DC + penumpukan/stok** → `sat_dc_stock_*` @ `dcname`, before Pareto/top-produk sell-in.
3. **Clarification chips** (`clarification_intents`) when one question names two governed metrics (e.g. bill-to-PO vs nilai penagihan grosir).
4. **Entity cheat sheet:** `sales_office` = Tempo sell-in cabang; `branch` = B2B partner DC sell-out; `dcname` = SAT stok DC partner (aligns to `branch` after normalization).

Numbers always execute via OSSIE `compile_governed` + Impala. PuppyGraph (Phase C7) is optional and not required here.

## B3 dry-run expectations

| ID | Expected resolver |
|----|-------------------|
| Q01–Q05, Q08, Q10 | `resolved` (governed) |
| Q06 | `needs_clarification` (DC vs store stock comparison — pick one metric, then the other) |
| Q07 | `needs_clarification` (promo ROI proxy choice) |
| Q09 | `needs_clarification` → chip **Picking** or **Unloading** → `average_*_minutes` @ `sales_off` |

Live: `bash scripts/run-b3-live.sh` from repo root (OSSIE-only backend recommended).

## PuppyGraph stub (C7)

`puppygraph_schema_stub.yaml` documents vertex/edge mapping to `gold.*`. Set `PUPPYGRAPH_ENABLED=true` and `PUPPYGRAPH_BASE_URL` when a service is deployed; `/health/ready` reports `puppygraph.schema_summary` (no traversal on Ask Data path yet).
