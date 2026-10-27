# TEMPO Management Question Coverage

**Status:** Candidate regression set, not yet a TEMPO management-approved question inventory.

## Current regression set

- Total prompts: 59 (includes catalog seed F1 with `catalog_question_id` + `chart_primary` + `domain_agent`)
- Supported: ~22 (incl. catalog_* governed)
- Supported with caveat: ~12
- Requires clarification: 2
- Unsupported by governed scope: ~22
- Blocked by governance: 1

See `ossie/golden_questions.yaml` for authoritative counts. Run `scripts/validate_tempo_impala_contract.py` after dependency install.

The unsupported set intentionally includes scope and safety boundaries:

- daily Sales
- January 2025 / outside Q4
- forecasting
- official margin
- promo-attributed revenue
- causal OOS claims
- monthly Sales Office trends
- free SQL

Three concrete metric gaps were identified:

1. governed distinct Material count for full Material 360 coverage
2. unfulfilled demand quantity (`PO - DO`)
3. governed distinct shared-customer count

These gaps must be added only after they are appended to the audited metric
catalog and reviewed by TEMPO business owners.

## Coverage target

Before default cutover:

1. Collect 30–50 real questions from TEMPO management.
2. Classify each as supported, supported-with-caveat, clarification, partial, or unsupported.
3. Achieve at least 80% supported coverage for priority in-scope questions.
4. Preserve explicit refusal for out-of-scope, causal, forecast, and free-SQL requests.

The regression set in `ossie/golden_questions.yaml` remains the technical
baseline while the real management inventory is collected.
