# UAT Process

**Status:** PLANNED — no formal UAT (User Acceptance Testing) sign-off process exists in current engineering documentation, beyond the general pre-push checklist in `docs/MASTER_PLAN.md` §13.

## Proposed UAT scope

Given the platform's current completion state (~55% overall, per the last audit), UAT in the traditional sense (business stakeholders validating a feature-complete product before launch) is premature for most of the platform today — UAT should be scoped incrementally, per completed capability, rather than held for a single end-of-project event.

## Proposed structure

1. **Feature-level UAT** — as each Priority-1/2 gap closes (per `docs/PRODUCTION_GAPS_REPORT.md`'s checklist), the relevant business stakeholder (Risk for credit changes, Finance for ledger changes, Compliance/Shariah board for contract changes) signs off that the fix behaves as intended from a business perspective, not just that the code runs.
2. **Full-flow UAT** — once the E2E test suite (see [`147-end-to-end-testing.md`](147-end-to-end-testing.md)) passes automatically for the happy path, a manual UAT pass with real (test-environment) stakeholders walking through the full 12-step flow as a final human check before any production/pilot launch decision.
3. **Regulatory/Shariah UAT** — distinct from general business UAT: the Shariah board's review (per [`../04-shariah/83-shariah-review-process.md`](../04-shariah/83-shariah-review-process.md)) functions as a form of UAT specifically for compliance, and should be a hard gate before launch, not a parallel-track nice-to-have.

## Related documents

[`155-release-acceptance-criteria.md`](155-release-acceptance-criteria.md), [`147-end-to-end-testing.md`](147-end-to-end-testing.md), [`../04-shariah/83-shariah-review-process.md`](../04-shariah/83-shariah-review-process.md).
