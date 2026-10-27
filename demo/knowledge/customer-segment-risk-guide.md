# Customer Segment and Risk Guide

**Version:** 1.0 (Golden Demo)  
**Disclaimer:** Synthetic demo content only. Not credit scoring, fraud scoring, or real risk policy.

## 1. Customer segmentation overview

Retail banking customers in the demo are grouped into three segments for service and analytics: Retail, Priority, and SME.

## 2. Retail customers

Standard mass-market customers with everyday banking needs. Marketing and service levels follow the baseline retail program.

## 3. Priority customers

**Priority Customer:** A higher-value retail customer segment receiving enhanced service treatment, including preferential queue handling and relationship manager access in this demo narrative.

## 4. SME customers

Small and medium enterprise customers with business accounts. SME segment reflects business banking packages and higher typical transaction volumes in the demo dataset.

## 5. Customer status definitions

| Status | Meaning |
|--------|---------|
| Active | Currently transacting or within normal engagement window. |
| Dormant | No recent activity; account remains open. |
| Closed | Relationship ended; no new activity expected. |

## 6. Risk tier definitions

| Tier | Demo meaning |
|------|----------------|
| Low | Standard monitoring. |
| Medium | Elevated review frequency in analytics scenarios. |
| High | Elevated monitoring requirements for demo analytical purposes. |

**High Risk:** A classification indicating elevated monitoring requirements for demo analytical purposes. It does not represent a real credit or fraud score.

## 7. Business interpretation guidance

When combining segment and risk tier, analysts should treat Priority and High Risk as a cue for enhanced monitoring in storytelling demos, not as automated real-world decisions.

A Priority customer with repeated failed transactions may warrant operational review under demo guidance, combining segment service expectations with payment reliability signals.

## 8. Example analytical questions

- How many Active Priority customers are in the High Risk tier?
- What share of SME customers are Dormant?
- Which cities have the highest count of Medium risk Retail customers?

## 9. Glossary

- **Segment:** Retail, Priority, or SME classification.
- **Risk tier:** Low, Medium, or High demo monitoring class.
- **Status:** Active, Dormant, or Closed lifecycle state.
