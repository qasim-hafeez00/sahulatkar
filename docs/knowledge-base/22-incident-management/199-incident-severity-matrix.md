# Incident Severity Matrix

**Status:** STABLE (proposed) — restates and formalizes the severity table already introduced in [`../12-operations/41-incident-response-plan.md`](../12-operations/41-incident-response-plan.md), as its own standalone reference since a severity matrix is typically consulted independently and quickly during an active incident, not read as part of a longer plan document.

## Matrix

| Severity | Definition | Response expectation | Example (grounded in this platform's known gaps) |
|---|---|---|---|
| SEV-1 | Customer money at risk, or platform-wide outage | Immediate, all-hands, incident commander declared | Duplicate payment processed; unbalanced ledger entry; VCN credential exposure |
| SEV-2 | Significant functional failure, workaround exists | Prompt response, may not require all-hands | Order stuck indefinitely on a missing callback; scraping worker down platform-wide |
| SEV-3 | Degraded but not blocking | Normal-priority response, tracked but not urgent | HITL queue backlog past SLA; one specific merchant's extraction failing |
| SEV-4 | Minor, no customer impact | Backlog item | Cosmetic admin dashboard bug, dead code path |

## Severity escalation/de-escalation

Not formally documented — a SEV-2 that turns out to have broader financial impact than initially assessed (e.g., "one merchant's extraction failing" turns out to correlate with a wider ledger issue) should have a clear, fast path to re-classify as SEV-1, rather than staying at its initial severity out of process inertia. Recommend this be made an explicit, named step in the incident policy.

## Related documents

[`198-incident-management-policy.md`](198-incident-management-policy.md), [`../12-operations/41-incident-response-plan.md`](../12-operations/41-incident-response-plan.md).
