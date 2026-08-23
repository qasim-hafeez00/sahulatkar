# Chargeback / Dispute Process

**Status:** PLANNED — this is the financial-operations-format companion to [`../02-business-workflows/54-chargeback-dispute-workflow.md`](../02-business-workflows/54-chargeback-dispute-workflow.md), which remains the primary document. This one focuses specifically on the Finance-team process angle (evidence submission, timelines, ledger treatment) rather than the workflow/trigger framing.

## Process steps (proposed, none currently implemented)

1. **Notification received** — from a gateway (Safepay/JazzCash/EasyPaisa), typically via webhook or settlement-file review.
2. **Case opened** — matched against the originating `payment_transactions` and the associated `loans`/`installments` record.
3. **Evidence gathered** — proof of authorization (contract signatures, OTP verification logs), proof of delivery (AfterShip tracking, delivery confirmation), and the customer's KYC-verified identity.
4. **Evidence submitted to the gateway** within whatever window that specific gateway's dispute process requires — **not documented for any of SahulatKar's three current gateways in this repository**; Finance should obtain and record each gateway's specific dispute-response SLA directly from the gateway's own merchant documentation.
5. **Outcome recorded** — won (charge stands) or lost (charge reversed, requiring a ledger reversal entry per [`107-reversal-rules.md`](107-reversal-rules.md) and a decision on the underlying loan's status).

## Why SahulatKar's evidence position is unusually strong for this specific product

Because every financing arrangement requires OTP-signed Wakalah and Murabaha contracts with full disclosure, and delivery is independently tracked via AfterShip, SahulatKar has a more complete evidence trail for "the customer knowingly authorized this" than a typical single-swipe card transaction would — this is worth Finance leaning on explicitly when contesting a dispute, since it directly addresses the most common chargeback reason code ("transaction not authorized by cardholder").

## Related documents

[`../02-business-workflows/54-chargeback-dispute-workflow.md`](../02-business-workflows/54-chargeback-dispute-workflow.md), [`107-reversal-rules.md`](107-reversal-rules.md).
