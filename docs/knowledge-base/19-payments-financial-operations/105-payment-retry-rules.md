# Payment Retry Rules

**Status:** STABLE (the schedule) — enforcement gap flagged.

## Installment auto-collection retry schedule

| Attempt | Timing |
|---|---|
| 1 (due date) | 9:00 AM |
| 2 (same day) | 6:00 PM |
| 3 (next day) | 9:00 AM |
| 4 (day+2) | 12:00 PM |
| After 4 fails | Flagged for manual collections outreach |

## Down payment retry

No fixed schedule — customer-initiated, can retry immediately from the payment screen with no cooldown documented.

## What determines whether a retry should even happen

Per [`103-failed-payment-handling.md`](103-failed-payment-handling.md), the schedule above assumes every failure is worth retrying on the same cadence — but a non-retryable failure (declined card, insufficient funds) retried 4 times on this schedule is 4 wasted attempts and 2 extra days of delay before the customer/collections team learns the real problem. **Recommend the retry schedule be conditioned on failure type** once retryable/non-retryable classification (`PO-BL-02`) is implemented — terminal failures should skip straight to customer notification rather than silently retrying.

## Enforcement status

The schedule above is documented policy; **the underlying trigger mechanism (an actual auto-debit attempt firing on the due date) is not implemented** (`LS-CRIT-04`) — see [`../02-business-workflows/52-installment-collection-workflow.md`](../02-business-workflows/52-installment-collection-workflow.md). This document describes the intended cadence for when that trigger exists.

## Related documents

[`103-failed-payment-handling.md`](103-failed-payment-handling.md), [`../02-business-workflows/52-installment-collection-workflow.md`](../02-business-workflows/52-installment-collection-workflow.md), [`../02-business-workflows/10-default-collections-workflow.md`](../02-business-workflows/10-default-collections-workflow.md).
