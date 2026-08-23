# Chargeback / Dispute Workflow

**Status:** PLANNED — like refunds, no chargeback-handling logic is referenced anywhere in current engineering documentation. This document identifies the gap and proposes a starting shape rather than describing working functionality.

## What a chargeback means in this platform's specific model

A chargeback would typically arise on the customer's down-payment or installment charge (via Safepay/JazzCash/EasyPaisa) — the customer disputes a charge with their card issuer or wallet provider, independent of anything SahulatKar does. This is distinct from a **merchant-side dispute**, which in this model means a third-party site refusing to honor a purchase, return, or warranty claim (see [`../02-business-workflows/06-merchant-vendor-journey.md`](../02-business-workflows/06-merchant-vendor-journey.md)) — the two are easy to conflate given the platform's unusual "we are both financier and purchasing agent" structure, so any policy written here should explicitly distinguish them.

## What exists today

Nothing specific to chargebacks. `payment_transactions.status` includes `chargeback` as a valid enum value in the schema (per `docs/System-md-files/M06-M09-payments-vcn-agent-hitl.md`), meaning the data model anticipated this scenario, but no service logic, admin workflow, or SOP references handling one.

## Trigger (target design)

A payment gateway notifies SahulatKar (via webhook or manual settlement-file review, given reconciliation currently runs on mock data per [`11-merchant-settlement-reconciliation.md`](11-merchant-settlement-reconciliation.md)) that a customer's card issuer has reversed a charge.

## Proposed steps (not yet implemented — for Finance/Product/Engineering to design)

1. Chargeback notification received → matched to the originating `payment_transactions` record.
2. Corresponding `installments`/`loans` record flagged, and the underlying financing arrangement re-assessed (has the product already shipped? has the customer already received value?).
3. Ledger correction entry — reversing recognized revenue if applicable.
4. Investigation: is this a legitimate dispute (customer genuinely never authorized/received) or a "friendly fraud" pattern? This should probably feed the Credit Engine's fraud signals (see [`18-credit-risk-policy/`](../18-credit-risk-policy/)) rather than being handled purely as a finance event.
5. Response/evidence submission to the gateway, within whatever window that gateway's own dispute process requires (Safepay/JazzCash-specific timelines not documented anywhere in this repo — Finance should confirm with each gateway directly).

## Open questions for Finance/Legal/Engineering

- Who owns chargeback response (Finance, Ops, or a dedicated role)?
- What's the SLA for responding to a gateway's chargeback notification before it auto-resolves against SahulatKar?
- How does a successful chargeback interact with the underlying loan — does the loan get cancelled, does the customer still owe the remaining balance through another payment method, does the product get treated as unpaid (with the merchant-return complexity that implies)?

## Related documents

[`../02-business-workflows/09-refund-cancellation-workflow.md`](../02-business-workflows/09-refund-cancellation-workflow.md) (the closest existing analog, also unimplemented), [`../11-compliance/38-responsible-financing-policy.md`](../11-compliance/38-responsible-financing-policy.md).
