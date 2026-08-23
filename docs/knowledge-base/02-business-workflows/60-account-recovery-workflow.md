# Account Recovery Workflow

**Status:** STABLE for the mechanical case (suspension lifted on condition resolved) · PLANNED for anything requiring an explicit customer-initiated appeal process, which is not documented anywhere in current engineering docs.

## Trigger

The condition that caused a suspension resolves — most commonly, an overdue installment is paid in full.

## Actors

Ledger Service (detects the resolving payment), Gateway (updates `users.status`), customer.

## Steps (for the payment-related case, the only one with a clear documented trigger)

1. Overdue installment paid → `installments.status = 'paid'`.
2. **Known gap:** no explicit logic is documented that automatically flips `users.status` back from `suspended` to `active` upon the triggering installment being cleared — this appears to be an implicit assumption in the design rather than a confirmed, tested transition. Recommend Engineering confirm this actually happens automatically, or whether it currently requires manual admin intervention.
3. Once active again, the user passes Layer 1's `account status != 'active'` check on their next order attempt.

## What's missing: an appeal/dispute path

For a suspension the customer believes was wrongly applied (e.g., a fraud false-positive, a payment that was actually made but not correctly recorded due to a reconciliation gap), there is no documented appeal or recovery request process — this would need to route through general customer support (itself not yet built, see [`57-customer-support-escalation-workflow.md`](57-customer-support-escalation-workflow.md)) and, for fraud-related suspensions, the blacklist-removal gap noted in [`58-fraud-detection-workflow.md`](58-fraud-detection-workflow.md) (no endpoint currently exists to remove a blacklist entry).

## Business rules

Recovery should require the same or lower burden of proof than the original suspension trigger — e.g., a payment-related suspension should lift automatically on payment with no additional friction, while a fraud-related suspension should require actual investigation before lifting, not an automatic timer. This principle is not documented explicitly anywhere in current engineering docs — recommend Risk/Compliance formalize it.

## Related documents

[`59-account-suspension-workflow.md`](59-account-suspension-workflow.md), [`58-fraud-detection-workflow.md`](58-fraud-detection-workflow.md), [`../16-customer-documentation/63-customer-states-statuses.md`](../16-customer-documentation/63-customer-states-statuses.md).
