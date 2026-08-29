# Postmortem Template

**Status:** STABLE (proposed template) — standalone version of the template already introduced in [`../12-operations/41-incident-response-plan.md`](../12-operations/41-incident-response-plan.md).

## Template

```markdown
## Incident Postmortem: [Title]

**Date:**
**Severity:** [SEV-1 / SEV-2 / SEV-3 / SEV-4]
**Duration:**
**Owner:**

### What happened?
[Factual timeline, no blame language]

### Why? (root cause, not just the proximate trigger)
[Distinguish the immediate cause from the underlying condition that allowed it —
 e.g., "a duplicate webhook double-confirmed a payment" is the proximate trigger;
 "no application-layer idempotency check exists" (GW-BL-13-adjacent) is the root cause]

### Impact?
[Customers affected, money involved, duration, any downstream effects
 — e.g., did this also corrupt a ledger entry, per LS-CRIT-02?]

### Root cause?
[The specific gap — reference an existing gap ID from docs/PRODUCTION_GAPS_REPORT.md
 if this incident is a manifestation of an already-known gap, rather than treating
 it as a brand-new discovery]

### Fix?
[What was done immediately to resolve this specific incident]

### Preventive action?
[What structural change prevents recurrence — not just "fixed this instance"]

### Owner?
[Who owns the preventive action]

### Deadline?
[When the preventive action will be complete]
```

## Why "reference an existing gap ID" is called out specifically

A meaningful fraction of this platform's plausible future incidents are **already predicted** by the gap inventory in `docs/PRODUCTION_GAPS_REPORT.md` and throughout this knowledge base (e.g., a duplicate-payment incident is a near-certain eventual consequence of `GW-BL-13` remaining open). A postmortem that treats such an incident as a novel surprise, rather than connecting it to the already-known gap, misses the chance to demonstrate — and act on — the fact that the platform's own documentation already predicted it. Recommend every postmortem explicitly check the existing gap inventory before writing "root cause" as if from scratch.

## Related documents

[`../12-operations/41-incident-response-plan.md`](../12-operations/41-incident-response-plan.md), `docs/PRODUCTION_GAPS_REPORT.md`.
