# Candidate metrics for Semantic Contract v2

Promote to [tempo_core.ossie.yaml](tempo_core.ossie.yaml) only after:

1. Exploratory Gold view deployed and row counts validated.
2. ≥2 golden questions in [golden_questions.yaml](golden_questions.yaml) pass as `supported`.
3. Business owner sign-off in [tempo_governance.yaml](tempo_governance.yaml).

| Candidate ID | Name | Source view | Catalog IDs | Status |
|--------------|------|-------------|-------------|--------|
| OOS-01 | material_oos_rate_month | `gold.rpt_sat_oos_month_exploratory` | O01, O02 | exploratory SQL only |
| PR-01 | promo_observation_count | `gold.rpt_promo_material_coverage_des` | P01 | exploratory |
| PR-02 | promo_material_december_sell_in_flag | join promo + stg sales Des | PQ1 | blocked until join audited |
| IDM-01 | dc_store_stock_qty | `gold.rpt_stock_sat_idm_exploratory` | I03, I05 | exploratory |
| SL-02 | unfulfilled_po_qty | PO − DO at material month | L05 gap | needs formula approval |

Audit trail: [datasets/audit/12_rpt_sat_oos_month_exploratory.sql](../../datasets/audit/12_rpt_sat_oos_month_exploratory.sql), [13](../../datasets/audit/13_rpt_sat_promo_december_exploratory.sql), [14](../../datasets/audit/14_rpt_stock_sat_idm_exploratory.sql).

**v1 unchanged:** 28 published metrics; orchestrator agents must not claim OOS/Promo/IDM as governed until promotion row status = `published`.
