# Golden Banking Demo — Phase 3 Semantic Layer

## Model

- **Name:** Retail Banking Analytics
- **Key:** `retail_banking_analytics`
- **Description:** Governed semantic model for Golden Banking customer and transaction analytics.
- **Source:** Banking PostgreSQL connector (`golden_banking_pg`) — schema `banking_demo` (no copy into SQLite/DuckDB).

## Data models

| Entity | Source table |
|--------|----------------|
| Customers | `banking_demo.customers` |
| Transactions | `banking_demo.transactions` |

## Relationship

- **Key:** `transactions_to_customers`
- **Join:** `a.customer_id = b.customer_id` (many transactions → one customer)
- **Type:** many-to-one, inner join

## Metrics

| Key | Business meaning |
|-----|------------------|
| `total_transaction_amount` | Sum of transaction amounts in scope |
| `transaction_count` | Count of transaction attempts |
| `average_transaction_value` | Average amount per transaction |
| `active_customers` | Distinct customers with `customer_status = 'Active'` |
| `failed_transaction_rate` | Failed attempts / total attempts (aligned with Knowledge) |

## Dimensions (minimum)

Transaction Month, Transaction Type, Channel, Merchant Category, Transaction Status, Customer Segment, Customer City, Risk Tier, Customer Status.

## Glossary

Priority Customer, Failed Transaction, High Risk, Transaction Attempt, Active Customer — definitions aligned with Phase 2 PDFs, with **Indonesian synonyms** (e.g. *transaksi gagal*, *nasabah aktif*) visible in Semantic Layer → Glossary.

## Publish workflow

1. Import entities from connector (Semantic Layer V2).
2. Add derived dimension `transaction_month`, metrics, relationship, glossary.
3. **Advanced → Model Health** (full validation, safe query probes).
4. **Publish to Ask Data** — stages OSSIE artifact under `runtime/cai-sim/var/semantic-runtime/` and activates deployment.

Bootstrap script: `python3 scripts/demo/register_banking_semantic.py` (requires `BANKING_DEMO_PG_PASSWORD` on backend).

## Example governed questions

- What is the total transaction amount?
- Show total transaction amount by channel.
- Which customer segment has the highest total transaction amount?
- What is the failed transaction rate?
- Show total transaction amount by month.

Use `@Retail Banking Analytics` (or explicit semantic model context) in Ask Data.

## Raw vs governed

Raw `@transactions` / `@customers` runs SQL against connector tables. Governed semantic uses published metrics/dimensions/relationships from the runtime artifact. Totals and rates should match equivalent raw SQL unless the metric applies explicit business logic (e.g. Active Customers uses `customer_status`, not “customers who transacted”).

## Knowledge vs semantic

- **@Retail Banking Knowledge:** explains policies (e.g. how Failed Transaction Rate is defined).
- **@Retail Banking Analytics:** computes governed metrics (e.g. Failed Transaction Rate value).

## Real `/chat` governed flow

Use explicit `@Retail Banking Analytics` (semantic model context) on Ask Data. The backend route is `/chat` with `context_mode=GOVERNED_SEMANTIC`, governed SQL compilation, and **Banking PostgreSQL** execution via connector binding (not Impala).

Evidence scripts:

- `scripts/demo/phase3_chat_governed_evidence.py` — core governed metrics
- `scripts/demo/banking_ask_tier_evidence.py` — presentation tier 1–3 + guardrails (writes `testing/evidence/golden-path/PHASE3-SEMANTIC/banking-ask-tier-matrix.json`)

### Patch auto-suggested metrics (UI import)

If the workspace uses auto-generated keys such as `customers_customer_id_total`, run:

```bash
python3 scripts/demo/patch_banking_auto_metrics.py
# or during golden re-register:
python3 scripts/demo/register_banking_semantic.py --patch-auto-metrics
```

This applies COUNT expressions, human labels, and Indonesian/English synonyms, then publishes.

## Datasource binding

Each imported entity stores `connection_id` (Banking PostgreSQL). Cloned/published versions must retain this binding; runtime deployment OSSIE artifacts drive governed SQL `FROM` clauses against `banking_demo.*`.

## Rollback procedure

1. Publish a harmless draft change (e.g. glossary wording) as a new version.
2. Note prior deployment id for Version 1 runtime.
3. `POST /api/v1/semantic/runtime/deployments/{v1_deployment_id}/rollback`
4. Verify `runtime_active_version` and governed `/chat` still succeed.

Script: `scripts/demo/phase3_semantic_rollback_evidence.py`

**Final demo runtime (after closure):** Version **1** deployment (`d4e15f94-…`).

## Acceptance

- Gates: `golden_path_banking_phase3_semantic_gate.py`, `golden_path_banking_phase3_closure_gate.py`
- Evidence: `testing/evidence/golden-path/PHASE3-SEMANTIC/` (including `browser/` PNGs A–M)
- Closure report: `docs/demo/PHASE3_SEMANTIC_CLOSURE_REPORT.md`
