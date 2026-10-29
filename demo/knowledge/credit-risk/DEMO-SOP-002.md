# DEMO-SOP-002: Synthetic Loan Portfolio Risk Monitoring

**Version:** 1.0
**Effective date:** 1 January 2025
**Owner:** Synthetic Portfolio Risk Monitoring Team
**Classification:** Synthetic Demo Only

## 1. Purpose

This SOP defines how synthetic loan-quality observations are categorized and analyzed for portfolio risk monitoring.

Its purpose is to demonstrate governed risk analytics and explainable AI-assisted investigation, not to establish actual banking compliance standards.

## 2. Scope and Data Grain

The SOP applies to the `loan_quality` dataset.

Each record represents one fictional loan at one assessment date. The dataset does not contain repeated monthly snapshots of the same loan.

Results may be analyzed by region, customer segment, origination channel, product category, and assessment period.

## 3. Risk Classification

Loans are categorized using `days_past_due`:

- **Low:** 0 days past due.
- **Medium:** 1–30 days past due.
- **High:** More than 30 days past due.

A loan is considered delinquent when `days_past_due` is greater than 30.

This is an internal synthetic demo definition, not a regulatory NPL classification.

## 4. Governed Portfolio Metrics

The official demo metrics are:

**Observed Loans:** The number of loan-quality observations within the requested scope.

**Delinquent Loans:** Observed loans with more than 30 days past due.

**Delinquency Rate:** Delinquent Loans divided by Observed Loans, expressed as a percentage.

**Total Outstanding:** The sum of outstanding balances for observed loans.

**Delinquent Balance:** The sum of outstanding balances for delinquent loans.

## 5. Monitoring and Escalation

For the demo, a segment is flagged for investigation when:

- Its delinquency rate exceeds **15%**, and
- The observed population contains at least **30 loans**.

These are synthetic monitoring triggers, not compliance limits or automatically enforced controls.

The risk team should compare the segment against the rest of the observed population and review the reporting period before drawing conclusions.

## 6. Investigation Workflow

When an elevated delinquency rate is detected:

1. Verify the metric and denominator.
2. Confirm the date range and sample size.
3. Break down results by region, segment, and product.
4. Compare the hotspot with a relevant reference population.
5. Document any limitation or uncertainty.
6. Escalate the finding for human risk review.

## 7. Important Limitations

Delinquency patterns alone do not establish a cause. The dataset does not provide customer repayment histories, macroeconomic explanations, collections actions, or regulatory provisioning measures.

The assistant must not infer that a specific customer is fraudulent or recommend an individual lending decision.

**Document status:** Approved for synthetic hackathon demonstration only.
