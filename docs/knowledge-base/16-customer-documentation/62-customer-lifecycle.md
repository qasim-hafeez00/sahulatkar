# Customer Lifecycle

**Status:** STABLE

## Lifecycle stages

```
Prospect (not yet registered)
  ↓
Registered (phone verified, users.status = 'pending_kyc')
  ↓
KYC pending → KYC verified (users.status = 'active')
  ↓
Eligible (passes a credit check for a given order — re-evaluated per order, not a permanent state)
  ↓
Active customer (has at least one order in progress)
  ↓
Active financing (has at least one loan with status='active' or 'partially_paid')
  ↓
Completed financing (loan reaches 'fully_paid')
  ↓
Repeat customer (returns for a second order)
```

## Mapping to `users.status`

| Lifecycle stage | `users.status` |
|---|---|
| Prospect | (no record yet) |
| Registered | `pending_kyc` |
| KYC verified onward | `active` |
| Suspended (see [`../02-business-workflows/59-account-suspension-workflow.md`](../02-business-workflows/59-account-suspension-workflow.md)) | `suspended` |
| Voluntarily or administratively closed | `closed` |
| Banned | `blocked` |

Note: `users.status` does not have a distinct value for "eligible," "active financing," or "completed financing" — those are derived states (computed from `loans`/`credit_applications` data joined against the user), not stored account-status values. Anyone building lifecycle-stage analytics should compute these from loan/order data, not expect them as a queryable `users.status` value.

## Credit-limit progression across the lifecycle

First order: capped at the cold-start maximum for the user's band (well below their nominal band limit). After N on-time payments (default 3), limit increases by a default 25% — see [`../03-bnpl-financing/15-credit-limit-rules.md`](../03-bnpl-financing/15-credit-limit-rules.md). This is the mechanism by which a "repeat customer" is meant to unlock more purchasing power over time.

## Churn / exit points

A customer can exit the lifecycle at multiple points: KYC rejection (with a 30-day re-application window), credit decline (re-evaluated on the next order attempt, not permanent), voluntary account closure (not documented as a self-service flow in current engineering docs — recommend confirming whether this exists), or `blocked` status (confirmed fraud/severe policy violation).

## Related documents

[`61-customer-persona.md`](61-customer-persona.md), [`63-customer-states-statuses.md`](63-customer-states-statuses.md), [`../02-business-workflows/05-customer-journey-e2e.md`](../02-business-workflows/05-customer-journey-e2e.md).
