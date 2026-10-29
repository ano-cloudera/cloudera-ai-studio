# DEMO-POL-001: Synthetic Credit Approval and Exception Policy

**Version:** 1.0
**Effective date:** 1 January 2025
**Owner:** Synthetic Credit Risk Governance Team
**Classification:** Synthetic Demo Only

## 1. Purpose

This policy defines the standard credit assessment rules used in the synthetic Credit Risk Intelligence dataset. It provides a consistent reference for explaining credit approval metrics, rejection patterns, and policy exceptions.

This policy is fictional and must not be used for real lending decisions.

## 2. Scope

This policy applies to the synthetic credit application population, including Retail, SME, and Priority segments across all six reporting regions.

The applicable products are Personal Loan, Working Capital, and Micro Loan.

## 3. Standard Approval Criteria

A credit application meets the standard approval criteria only when:

- Credit score is at least **650**.
- Debt-to-income ratio (DTI) is no greater than **0.45**, or 45%.

Applications failing either condition are normally rejected under the synthetic standard decision logic.

A policy exception may allow an application to be approved despite failing one or both criteria.

## 4. Policy Exception Handling

An approved application outside the standard thresholds must be recorded using `policy_exception_flag = TRUE`.

The exception flag provides a reporting indicator, not evidence that a real approval authority, justification document, or regulatory approval exists.

The synthetic dataset records whether an exception occurred but does not record the approver, supporting documentation, or approval workflow.

Exceptions should be reviewed in aggregate by reporting period, customer segment, region, and application channel.

## 5. Monitoring Indicators

The Credit Risk Governance Team should monitor:

- Approval rate and rejection rate.
- Average credit score and average DTI.
- Number of approved policy exceptions.
- Regional and channel-level differences in approval outcomes.
- Average decision-processing time.

For this demonstration, an approval-rate difference greater than **15 percentage points** between a selected group and a relevant comparison group is a trigger for further investigation, not proof of a policy breach.

## 6. Investigation Procedure

When an unusual approval pattern is identified:

1. Confirm the reporting period and population.
2. Compare approval rates with an appropriate reference group.
3. Review credit scores and DTI distributions.
4. Check the number of policy exceptions.
5. Escalate suspected causes for further analysis.

The analytics assistant must distinguish observed correlations from confirmed causes.

## 7. Limitations

The synthetic dataset does not contain real borrower identities, real credit-bureau scores, regulatory records, or complete underwriting documentation.

No automated credit decision may be made from this policy or dataset.

**Document status:** Approved for synthetic hackathon demonstration only.
