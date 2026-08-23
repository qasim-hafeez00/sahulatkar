# Business Continuity

**Status:** PLANNED — no business continuity plan exists in current documentation. This is distinct from disaster recovery ([`161-disaster-recovery.md`](161-disaster-recovery.md), which is technical/infrastructure recovery) — business continuity covers **operational** continuity: can the business keep functioning (even in a degraded mode) while technical recovery happens.

## What business continuity should cover for SahulatKar specifically

- **Manual fallback for automated processes during an outage.** If Payment Orchestrator is down, can down payments still be collected manually (bank transfer, in-person)? If the credit engine is down, is there a documented manual-underwriting fallback, or does the business simply stop accepting new orders until it's back? Neither is documented today.
- **Collections continuity.** If the billing sweep or Notification Service is down for an extended period, is there a manual process to keep the collections escalation timeline moving (see [`../02-business-workflows/10-default-collections-workflow.md`](../02-business-workflows/10-default-collections-workflow.md)) rather than letting it silently pause? A paused collections process during an outage has real financial consequence (delayed recovery) distinct from a paused *new-sales* process.
- **HITL team continuity.** The checkout-automation HITL queue and KYC manual-review queue both depend on human operators — what's the staffing continuity plan (backup on-call, cross-training) if the primary team is unavailable?
- **Communication continuity.** If Notification Service is down, how are customers informed of an outage or delay? Currently no documented alternate channel.

## Relationship to the platform's current maturity stage

Given the platform is ~55% complete overall (per the last audit) and several "automated" processes are actually not automatic yet (installment auto-collection, refunds), the business is arguably *already* operating with informal manual fallbacks for these gaps today — this document's real near-term value is making those informal fallbacks explicit and documented, not waiting for a hypothetical future outage to force the question.

## Related documents

[`161-disaster-recovery.md`](161-disaster-recovery.md), [`../12-operations/41-incident-response-plan.md`](../12-operations/41-incident-response-plan.md), [`../02-business-workflows/10-default-collections-workflow.md`](../02-business-workflows/10-default-collections-workflow.md).
