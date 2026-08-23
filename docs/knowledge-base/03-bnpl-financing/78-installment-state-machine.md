# Installment State Machine

**Status:** STABLE — the installment-specific slice of [`16-financing-state-machine.md`](16-financing-state-machine.md), expanded with the transition triggers that document only summarizes.

## States and transition triggers

```
pending
  → paid          [triggered by: successful gateway charge, webhook-confirmed]
  → overdue       [triggered by: due_date passed with status still pending]
    → defaulted   [triggered by: exceeds a default day-count threshold — NOT explicitly specified in current docs]
  → waived        [triggered by: admin/collections decision, e.g. goodwill or hardship]
  → rescheduled   [triggered by: admin-approved restructuring — NOT YET IMPLEMENTED, see GW-GAP-05]
```

## Field-level tracking through the states

`days_overdue` increments daily while `overdue`. `retry_count` and `next_retry_at` track the auto-collection retry cadence (see [`../02-business-workflows/08-payment-workflow.md`](../02-business-workflows/08-payment-workflow.md)). `late_fee_amount` accrues once overdue and is 100% charity-routed on eventual payment.

## The undocumented threshold

Nothing in current engineering docs specifies exactly how many days overdue an installment must be before transitioning from `overdue` to `defaulted` — the collections escalation timeline (D+1 through D+60) describes *actions taken* at each day but doesn't map a specific day to the `defaulted` status transition itself. **Recommend Risk explicitly define this threshold** — it matters for both the loan-level `defaulted` status trigger and for TASDEEQ negative reporting timing (currently tied to the D+30 "formal notice" stage per the escalation table, which may or may not be the same moment the installment record itself flips to `defaulted`).

## Relationship to loan status

An individual installment reaching `overdue`/`defaulted` does not automatically mean the whole loan is `defaulted` — a loan can be `partially_paid` with one overdue installment while others remain current. The loan-level `defaulted` status is presumably triggered by some aggregate condition (e.g., any installment reaching `defaulted`, or a certain proportion) — this rollup rule is likewise not explicitly documented and should be confirmed.

## Related documents

[`16-financing-state-machine.md`](16-financing-state-machine.md), [`../02-business-workflows/10-default-collections-workflow.md`](../02-business-workflows/10-default-collections-workflow.md), [`../02-business-workflows/53-missed-payment-workflow.md`](../02-business-workflows/53-missed-payment-workflow.md).
