# Release Acceptance Criteria

**Status:** STABLE as a **proposed gate** — no formal release-acceptance checklist exists today beyond the pre-push checklist in `docs/MASTER_PLAN.md` §13 (which governs individual commits, not a release/launch decision). This document proposes the launch-specific gate.

## Proposed criteria before any real-money production launch

- [ ] All Priority-1 (launch-blocking) items in `docs/PRODUCTION_GAPS_REPORT.md` §13 closed and verified.
- [ ] The debit=credit ledger invariant enforced in code, not just in the schema's intent (`LS-CRIT-02`).
- [ ] `loan.created` published and consumed correctly for every signed Murabaha contract.
- [ ] Refund pathway functional end to end.
- [ ] The E2E happy-path test (see [`147-end-to-end-testing.md`](147-end-to-end-testing.md)) passes automatically in CI.
- [ ] Shariah board has reviewed and ruled on the tiered-markup open item (see [`../04-shariah/19-shariah-review-register.md`](../04-shariah/19-shariah-review-register.md)) — no launch with an unresolved pricing-approval gap.
- [ ] NADRA/Shufti Pro integrations are live (not stubs) — a launch with stubbed KYC identity verification is a materially different risk posture than what the product's compliance story assumes.
- [ ] Observability (at minimum: alerting on payment/ledger/DLQ failures) is operational — launching with zero automated incident detection (current state per [`../10-devops/35-monitoring-logging.md`](../10-devops/35-monitoring-logging.md)) is not an acceptable risk posture for a platform moving real customer money.
- [ ] Secret rotation mechanism exists, or an explicit, leadership-accepted risk exception is documented for launching without one.
- [ ] Legal has confirmed SahulatKar's actual licensing/regulatory status with SECP (currently unconfirmed anywhere in this repository, per [`../11-compliance/36-compliance-requirements-matrix.md`](../11-compliance/36-compliance-requirements-matrix.md)).

## Why this list is deliberately stricter than "all P1 gaps closed"

Several items above (Shariah board sign-off, NADRA going live, legal licensing confirmation) aren't in `docs/PRODUCTION_GAPS_REPORT.md` at all, because that report is a *code* audit, not a launch-readiness audit — this document exists specifically to catch the business/legal/compliance gates a pure code audit wouldn't surface, alongside the engineering gates it would.

## Related documents

`docs/PRODUCTION_GAPS_REPORT.md`, [`154-uat-process.md`](154-uat-process.md), [`../11-compliance/36-compliance-requirements-matrix.md`](../11-compliance/36-compliance-requirements-matrix.md), [`../04-shariah/19-shariah-review-register.md`](../04-shariah/19-shariah-review-register.md).
