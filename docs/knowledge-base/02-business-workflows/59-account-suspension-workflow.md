# Account Suspension Workflow

**Status:** STABLE (mechanism) — the *triggering policy* (exactly which conditions cause a suspension) is thinner in current documentation than the mechanism itself; gaps flagged below.

## Trigger

`users.status` transitions to `suspended`. Known triggers referenced across engineering docs: entering the +7-day collections escalation stage ("account restriction — no new purchases," see [`10-default-collections-workflow.md`](10-default-collections-workflow.md)), a confirmed fraud/blacklist action (see [`58-fraud-detection-workflow.md`](58-fraud-detection-workflow.md)), or a manual admin action.

## Actors

Ledger/collections process (for payment-related suspension), fraud_analyst (for fraud-related suspension), operations_manager (manual).

## Steps

1. `users.status` set to `suspended` — this immediately fails Layer 1 hard blocks for any new order (`Account status != 'active'`), blocking all new purchases.
2. Existing active loans are **not** automatically affected by a suspension — a suspended user's existing installments continue on their normal schedule; suspension blocks new activity, not existing obligations.
3. Customer notification — **known gap:** no dedicated suspension-notification event exists in the event catalog (see [`../06-api-events/24-event-catalog.md`](../06-api-events/24-event-catalog.md)); confirm whether one is sent via a different mechanism or not at all.

## Business rules

A suspended user's `available_credit` remains functionally irrelevant since Layer 1 blocks any new order regardless of limit. Suspension is distinct from `blocked` (a harder status, implying account closure/ban rather than a temporary restriction) — the two-tier distinction exists in the `users.status` CHECK constraint (`pending_kyc`/`active`/`suspended`/`closed`/`blocked`) but the specific policy differences between `suspended` and `blocked` (duration, reversibility, who can apply each) are not documented — recommend Risk/Compliance define this explicitly.

## System services involved

Gateway (owns `users.status`), Credit Engine (enforces the block at Layer 1).

## Failure cases

A suspended user attempting a new purchase receives a clear decline via the standard credit-check path — no separate error handling needed, since it's the same hard-block mechanism as any other Layer 1 condition.

## Expected outcome

User is blocked from new purchases while existing obligations continue; suspension is lifted (returns to `active`) once the triggering condition resolves (e.g., overdue installment paid).

## Related documents

[`60-account-recovery-workflow.md`](60-account-recovery-workflow.md), [`10-default-collections-workflow.md`](10-default-collections-workflow.md), [`../16-customer-documentation/63-customer-states-statuses.md`](../16-customer-documentation/63-customer-states-statuses.md).
