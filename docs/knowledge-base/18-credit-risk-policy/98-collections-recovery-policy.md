# Collections & Recovery Policy

**Status:** STABLE (the escalation mechanism) — recovery/write-off *policy* beyond the trigger table is a documented gap.

## The escalation timeline (mechanism, fully specified)

See [`../02-business-workflows/10-default-collections-workflow.md`](../02-business-workflows/10-default-collections-workflow.md) for the complete D-7 through D+60 table. This document covers the policy layer around that mechanism.

## Recovery approach by stage

| Stage | Recovery posture |
|---|---|
| D-7 to D0 | Preventive — reminders only, no collections action |
| D+1 to D+7 | Soft collections — automated reminders, retry attempts, then a human call at D+7 |
| D+15 | Restrictive — no new purchases, but existing installment obligations continue normally |
| D+30 | Formal — registered notice, negative credit bureau (TASDEEQ) reporting |
| D+60 | Recovery — write-off review, legal proceedings |

## What's genuinely missing: a hardship/restructuring path

Per [`../11-compliance/38-responsible-financing-policy.md`](../11-compliance/38-responsible-financing-policy.md), there is currently no mechanism — policy or technical — for a customer facing genuine hardship to get anything other than the standard escalation timeline. Payment restructuring (`GW-GAP-05`) is speced as an admin capability but not built. **A responsible collections policy should distinguish "won't pay" from "can't pay right now"** and offer the latter group a different path (payment plan extension, temporary reduced payment) before proceeding down the same punitive track as the former — this distinction does not currently exist anywhere in engineering documentation or code.

## Write-off policy (genuinely undocumented beyond one line)

"D+60: Write-off review → Legal proceedings" is the entirety of what's documented. No policy exists specifying: the accounting treatment (when principal is formally written off vs. merely provisioned against), the loss-provisioning trigger point, what "legal proceedings" concretely means in the Pakistani context (small claims court? a collections agency? something else?), or whether/when a written-off debt might be sold to a third-party collector. **Finance/Legal should author a dedicated write-off policy** — this gap is also flagged in [`../02-business-workflows/10-default-collections-workflow.md`](../02-business-workflows/10-default-collections-workflow.md).

## Charity-routing constraint on collections economics

Because 100% of late fees are charity-routed rather than retained, collections activity generates **no direct revenue** for SahulatKar beyond eventually recovering the original principal + profit — meaning the entire cost of running collections (calls, notices, legal proceedings) is a pure cost center, not offset by late-fee income the way it might be at a conventional lender. This should factor into how aggressively collections is resourced/automated relative to the value actually recovered.

## Related documents

[`../02-business-workflows/10-default-collections-workflow.md`](../02-business-workflows/10-default-collections-workflow.md), [`../11-compliance/38-responsible-financing-policy.md`](../11-compliance/38-responsible-financing-policy.md), [`../12-operations/`](../12-operations/) SOPs.
