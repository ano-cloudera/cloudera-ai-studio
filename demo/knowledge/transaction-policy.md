# Retail Banking Transaction Policy

**Version:** 1.0 (Golden Demo)  
**Effective date:** 2026-01-01  
**Disclaimer:** Synthetic demo content only. Not real bank policy or legal advice.

## 1. Purpose

This document defines business meanings for transaction status, channels, and types used in the Golden Path retail banking demo. It complements structured transaction data; it does not replace core banking systems.

## 2. Transaction status definitions

### Successful transaction (SUCCESS)

A transaction completed successfully and is included in completed transaction value calculations unless another metric explicitly states otherwise.

### Failed transaction (FAILED)

A transaction that did not complete successfully. Failed transactions are counted in operational monitoring but are excluded from completed value totals by default.

### Pending transaction (PENDING)

A transaction awaiting final processing. Pending items must not be treated as completed value by default until status changes to SUCCESS.

## 3. Channel definitions

| Channel | Description |
|---------|-------------|
| Mobile Banking | Customer-initiated activity through the mobile application. |
| Internet Banking | Customer-initiated activity through the web banking portal. |
| ATM | Automated teller machine, including cash withdrawal and balance inquiry. |
| Branch | Over-the-counter service at a physical branch. |
| EDC | Electronic data capture at merchants (card-present retail). |

## 4. Transaction type definitions

- **Transfer:** Movement of funds between accounts.
- **Payment:** Outbound payment to a beneficiary or biller.
- **Purchase:** Merchant or retail spend.
- **Withdrawal:** Cash outflow, commonly via ATM or branch.
- **Deposit:** Cash or check deposit increasing balance.

## 5. Transaction monitoring considerations

Operations teams review failed and pending volumes by channel daily. Spikes in FAILED activity on a channel may indicate infrastructure or fraud-pattern review triggers in this demo scenario.

## 6. Example business rules

**Completed value:** Sum of SUCCESS transaction amounts unless the analysis explicitly includes other statuses.

**Failed Transaction Rate:** The number of failed transactions divided by total transaction attempts (SUCCESS + FAILED + PENDING counted as attempts unless a report excludes PENDING).

**Pending exposure:** PENDING amounts are tracked separately and excluded from completed totals until settled.

## 7. Glossary

- **Attempt:** Any transaction row regardless of final status.
- **Completed value:** SUCCESS amounts under default rules.
- **Channel mix:** Distribution of attempts or value across Mobile Banking, Internet Banking, ATM, Branch, and EDC.
