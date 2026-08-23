# Default SOP

**Status:** STABLE (for the specified escalation stages) — write-off stage is thin, per the same gap noted in [`../18-credit-risk-policy/98-collections-recovery-policy.md`](../18-credit-risk-policy/98-collections-recovery-policy.md).

## Staff actions by escalation stage

| Day | System action | Staff action required |
|---|---|---|
| −7 to −1 | Automated reminders fire | None — monitor only |
| 0 | Auto-debit attempted (once implemented) | None |
| +1 to +3 | Automated retries + soft/firm notices | None — monitor for patterns (e.g., a customer with a history of always paying by +3 shouldn't necessarily be treated the same as a first-time miss) |
| +7 | Account restriction | **Human call required** — this is the first stage requiring active staff action, not just system automation |
| +15 | Legal warning notice | Confirm the notice was actually sent (given notification gaps elsewhere in the platform, don't assume automation handled this correctly without verification) |
| +30 | Formal notice + negative TASDEEQ report | Confirm TASDEEQ reporting actually occurred (live-integration status is unconfirmed per [`../06-api-events/124-external-integration-documentation.md`](../06-api-events/124-external-integration-documentation.md)) |
| +60 | Write-off review begins | Escalate to Finance/Legal — **no documented write-off procedure exists beyond this trigger point**, see [`../18-credit-risk-policy/98-collections-recovery-policy.md`](../18-credit-risk-policy/98-collections-recovery-policy.md) |

## What to check before escalating a case

Given the platform's known gap where auto-collection may not actually be firing (`LS-CRIT-04`), **verify an actual charge attempt was made** before treating a customer as "won't pay" — a customer whose installment simply was never attempted (a system gap) is a fundamentally different case from one who genuinely defaulted, and should not proceed down the same escalation path.

## Hardship consideration

Per [`../11-compliance/38-responsible-financing-policy.md`](../11-compliance/38-responsible-financing-policy.md), there's currently no formal hardship/restructuring option — but staff exercising judgment (e.g., pausing escalation for a customer who proactively contacts support explaining genuine hardship) is a reasonable interim practice even without a formal system-supported restructuring path, and should be documented case by case until a real policy exists.

## Related documents

[`../02-business-workflows/10-default-collections-workflow.md`](../02-business-workflows/10-default-collections-workflow.md), [`../18-credit-risk-policy/98-collections-recovery-policy.md`](../18-credit-risk-policy/98-collections-recovery-policy.md).
