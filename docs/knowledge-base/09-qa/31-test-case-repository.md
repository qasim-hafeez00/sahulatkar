# Test Case Repository

**Status:** STABLE as a **starting scenario catalog**, built from the 2026-04-27 code audit's scenario walkthroughs (`docs/PRODUCTION_GAPS_REPORT.md` §1) rather than from an existing formal test-case management tool — none is referenced in current engineering docs. Treat this as the seed for a real test-case repository (in whatever tool QA adopts), not a replacement for one.

## Why these scenarios specifically

The audit's scenario walkthroughs are uniquely valuable as test-case seeds because each was produced by tracing actual code, not by imagining happy paths — meaning every scenario below already has at least one known real gap attached, which is exactly the highest-value place to start regression/E2E coverage.

## Scenario A: Happy Path — Full Order Completion

Steps 1–12 of the standard flow (see [`../02-business-workflows/07-bnpl-workflow-e2e.md`](../02-business-workflows/07-bnpl-workflow-e2e.md)). **This scenario cannot currently pass end-to-end** — it will fail at step 2 (scraping worker crash, `PS-BUG-01`) before ever reaching later steps. As those blockers close, this remains the single most important scenario to keep passing in CI, since it's the platform's core value proposition.

Sub-scenarios worth their own test cases as the gaps close: concurrent double-order credit exhaustion (`GW-BL-01`), Wakalah-skip-to-Murabaha (`GW-BL-03`), VCN issuance failure with no rollback (step 9 gap), checkout failure without VCN void (step 10 gap), delivery confirmation not triggering installment activation (step 11 gap), billing sweep not triggering auto-collection (step 12 gap).

## Scenario B: User Cancels Order After Offer Accepted

Test the cancellable-state boundary explicitly: cancellation should succeed in `url_received`/`offer_presented`/`offer_accepted`/`extraction_failed` (implemented) and currently incorrectly has no path from `contracts_signed` pre-VCN (`GW-BL-04` — write a test that currently documents this as a known failure, then flips to a regression test once fixed). Also test: credit restoration on cancel does not incorrectly grant credit that was never reserved (currently broken due to `GW-BL-01`), and that a cancellation notification is sent (currently missing, `GW-BL-10`).

## Scenario C: KYC Rejection and Resubmission

Test: resubmission clears prior NADRA/Shufti data correctly; resubmission does not orphan a still-claimed manual-review queue item (`GW-BL-09`); the 3-attempt cap cannot be reset by creating a new account with the same CNIC. Note NADRA/Shufti are stubs in the current build (see [`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md)) — tests against real vendor behavior will need to wait for those integrations, or be written against documented mock contracts in the meantime.

## Scenario D: Payment Failure Mid-Installment

Test: reminder fires D-3/D-1 before due date; on due date, an actual charge attempt fires (currently does not — `LS-CRIT-04`/missing `auto-collect` endpoint); after repeated failures, escalation to HITL or credit-bureau reporting occurs (currently does not).

## Financial-transaction-specific scenarios

See [`32-financial-transaction-test-strategy.md`](32-financial-transaction-test-strategy.md) — kept separate because financial correctness testing has different rigor requirements (exact-decimal assertions, ledger-balance invariants, idempotency-under-concurrency) than general functional testing.

## Cross-service integration scenarios (from audit §12.2, "Missing Integration Points")

Each row in that table is a candidate integration test:

- Product extracted → order updated (retry-on-Gateway-down case is currently untested/unimplemented)
- Payment confirmed → order status (saga-compensation-on-partial-failure case)
- VCN issued → checkout triggered (race condition if order cancelled mid-issuance)
- Delivery confirmed → order delivered (installment-activation trigger, currently missing)
- Installment overdue → auto-collect (currently missing entirely)
- Installment overdue → user notification (currently missing entirely)
- Contract signed → `loan.created` event → ledger entries (currently missing entirely — the highest-priority integration test to write, since it silently breaks the books for every loan)
- Order cancelled → VCN voided (currently missing entirely)

## Suggested repository structure going forward

Group by the 12-step flow stage a scenario primarily exercises, tag each with the gap ID(s) it currently fails against (from `docs/PRODUCTION_GAPS_REPORT.md`), and track a scenario as "red" until the underlying gap closes rather than skipping/deleting it — this keeps the test suite honest about what actually works.

## Related documents

[`30-qa-strategy.md`](30-qa-strategy.md), [`32-financial-transaction-test-strategy.md`](32-financial-transaction-test-strategy.md), `docs/PRODUCTION_GAPS_REPORT.md` §1.
