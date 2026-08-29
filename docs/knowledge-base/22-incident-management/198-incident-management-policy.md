# Incident Management Policy

**Status:** PLANNED — the governing policy document for [`../12-operations/41-incident-response-plan.md`](../12-operations/41-incident-response-plan.md), which covers the operational playbook; this document covers the policy layer (roles, authority, communication obligations) above it.

## Why a separate policy document, distinct from the response plan

[`../12-operations/41-incident-response-plan.md`](../12-operations/41-incident-response-plan.md) answers "what do we do when X happens." This document is meant to answer the governance questions a playbook alone doesn't: who declares an incident, who has authority to make customer-impacting decisions during one (e.g., pausing new orders platform-wide), and what the organization commits to regarding post-incident transparency — none of which is currently documented anywhere.

## Proposed policy elements

- **Incident declaration authority** — who can formally declare a SEV-1/2 incident (proposed: any engineer can declare, but only a designated incident commander role can *resolve/close* one).
- **Decision authority during an incident** — e.g., who can authorize pausing new order intake platform-wide, given the platform currently has no documented "kill switch" process for a scenario like a confirmed ledger-corruption bug actively affecting new transactions.
- **Communication commitments** — internal (who gets notified, how fast) and external (does SahulatKar commit to customer-facing status communication during an incident? Not documented anywhere today).
- **Regulatory notification triggers** — an incident touching customer PII or funds may separately trigger the data-breach and regulatory-reporting obligations noted in [`../11-compliance/169-data-protection-compliance.md`](../11-compliance/169-data-protection-compliance.md) and [`../11-compliance/172-regulatory-reporting-procedure.md`](../11-compliance/172-regulatory-reporting-procedure.md) — this policy should explicitly cross-reference those triggers rather than leaving incident response and regulatory compliance as separately-run processes that might miss each other.

## Related documents

[`../12-operations/41-incident-response-plan.md`](../12-operations/41-incident-response-plan.md), [`199-incident-severity-matrix.md`](199-incident-severity-matrix.md), [`../11-compliance/172-regulatory-reporting-procedure.md`](../11-compliance/172-regulatory-reporting-procedure.md).
