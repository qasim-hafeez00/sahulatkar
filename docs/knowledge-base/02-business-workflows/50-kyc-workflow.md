# KYC Workflow

**Status:** STABLE — this is the workflow-format companion to [`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md), which remains the authoritative technical spec (thresholds, vendor notes, rejection codes). This document exists to satisfy the "workflow" documentation slot specifically — trigger/actors/preconditions/steps/failure-cases format — for readers who think in workflows rather than technical pipelines.

## Trigger

`users.status = 'pending_kyc'` and the user opens the KYC flow (either immediately post-registration or later, before their first purchase attempt).

## Actors

Customer, Gateway, NADRA Verisys, Shufti Pro/liveness vendor, KYC Ops (compliance_officer role, conditional).

## Preconditions

Registered account with a verified phone number.

## Steps, business rules, and failure cases

Identical to the pipeline described in [`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md) — see that document for the full 10-step pipeline, tier structure, manual-review thresholds, and rejection codes. This document does not duplicate that content; it exists purely to make the workflow discoverable under "Business Workflows" for readers browsing by category rather than by system layer.

## Expected outcome

KYC approved (credit scoring triggered) or rejected (customer notified, may re-apply after 30 days).

## Related documents

[`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md) (authoritative spec), [`49-customer-onboarding-workflow.md`](49-customer-onboarding-workflow.md).
