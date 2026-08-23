# Failed Payment Handling

**Status:** STABLE (retry mechanism) — see [`104-settlement-schedule.md`](104-settlement-schedule.md) and [`105-payment-retry-rules.md`](105-payment-retry-rules.md) for the adjacent detail this document doesn't duplicate.

## Failure at each payment moment

| Moment | What "failed" means | Handling |
|---|---|---|
| Down payment | Gateway declines or times out before contract-to-payment flow completes | Order remains at `contracts_signed`; customer can retry from the payment screen with no additional friction |
| Installment (auto-collection, once built) | Auto-debit attempt fails on due date | Retry per [`105-payment-retry-rules.md`](105-payment-retry-rules.md) schedule, then flagged for manual collections outreach |
| Installment (manual, current actual path) | Customer-initiated `POST /payments/installment/{id}/pay` fails | Customer sees an immediate error, can retry manually — **no dedicated retry endpoint currently exists** (`GW-GAP-10`) |
| VCN issuance | Issuer (Stripe) unavailable or declines | **Known gap:** order status does not roll back, no admin retry endpoint exists (`PO-CRIT-04` family) |

## Retryable vs. non-retryable distinction (the core handling gap)

As noted in [`100-payment-lifecycle.md`](100-payment-lifecycle.md), the platform does not currently distinguish a transient failure (network timeout — retry makes sense) from a terminal one (insufficient funds, invalid card — retrying is pointless and may frustrate the customer) — both increment `attempt_count` identically (`PO-BL-02`). A correct failed-payment-handling design should branch on this distinction: terminal failures should surface a clear, specific reason to the customer immediately rather than silently queueing a retry that will predictably fail again.

## Escalation on repeated failure

After 3 failed attempts (tracked via `attempt_count`), **no escalation to HITL or credit-bureau reporting currently exists** — this is a specific, named gap from the audit's Scenario D walkthrough. The design intent (per the collections escalation timeline) is that repeated failure should eventually trigger the +7/+15/+30-day escalation steps, but the mechanical link from "3rd failed attempt" to "start the formal escalation clock" is not confirmed as wired.

## Related documents

[`100-payment-lifecycle.md`](100-payment-lifecycle.md), [`105-payment-retry-rules.md`](105-payment-retry-rules.md), [`../02-business-workflows/53-missed-payment-workflow.md`](../02-business-workflows/53-missed-payment-workflow.md).
