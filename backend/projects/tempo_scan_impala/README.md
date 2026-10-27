# Tempo Scan Impala Semantic Profile

This project is the additive, default-off real-data profile for TEMPO Q4 2024.
It must not replace or mutate `projects/tempo_scan` until the cutover gates pass.

## Source contract

- Impala database: `gold`
- Semantic source views:
  - `gold.rpt_sap_monthly_executive_semantic`
  - `gold.rpt_sap_material_month_semantic`
  - `gold.rpt_service_level_material_month_semantic`
  - `gold.rpt_sap_customer_reconciliation_semantic`
  - `gold.rpt_sales_office_performance_semantic`
- Runtime metric metadata: `gold.rpt_semantic_metric_catalog`
- Source-controlled definitions: `datasets/audit/`

## Safety rules

1. Default project remains `tempo_scan`.
2. Default semantic execution remains legacy until explicitly configured.
3. No free SQL and no runtime-invented joins.
4. Every analytical answer must resolve to a published metric and source view.
5. Pending metrics must be labeled as candidates, not official business KPIs.
6. Official revenue is Gold Gross Billing Value (`BILL_VAL`) in IDR.
7. Sell-In and Sell-Out are separate stages; never add them as one revenue figure.
8. PuppyGraph is out of scope for this phase.

## Planned runtime flags

```text
PROJECT_ID=tempo_scan_impala
DATA_BACKEND=impala
SEMANTIC_EXECUTION_MODE=ossie
```

These values are opt-in. Existing deployment behavior must remain unchanged when
they are absent.

## Multi-agent (Agent Studio)

Master Orchestration + 9 domain agents: [agents/README.md](agents/README.md).

## Delivery gates

1. OSSIE Core model validates.
2. Golden questions pass (59 prompts in `ossie/golden_questions.yaml`, target ≥50).
3. Impala shadow execution reconciles with audited Gold values.
4. Dashboard/API contract tests pass.
5. Business owners review candidate metrics.
6. Cutover receives explicit approval.
