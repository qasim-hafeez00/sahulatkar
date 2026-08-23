# End-to-End Testing

**Status:** PLANNED — explicitly named as a Phase 4 target in `docs/MASTER_PLAN.md` §8 ("Comprehensive E2E Integration Suite") and not yet built per the audit.

## Target scope

A Playwright-driven test suite exercising the full 12-step order flow across all 6 backend services and both frontends — from URL paste through final installment payment — end to end, against a real (test) environment rather than mocked service boundaries.

## Why this is the single highest-leverage testing investment available right now

Every individual gap documented throughout this knowledge base (the scraping worker crash, the incomplete checkout form-filler, the missing `loan.created` event, the un-triggered billing sweep) was discovered by a **manual, one-time code audit** — not by an automated test that runs on every push. A working E2E suite covering Scenario A (happy path, per [`31-test-case-repository.md`](31-test-case-repository.md)) would have caught most of these Priority-1 gaps automatically and continuously, rather than requiring a point-in-time forensic review to surface them.

## Recommended build order

1. Stand up the E2E environment first (docker-compose with all 6 services + testcontainers-managed Postgres/Redis) — this alone is meaningful infrastructure investment.
2. Write the happy-path test for Scenario A, expecting it to **fail** initially against the current codebase (this is fine — a red E2E test documenting a real gap is valuable output, not a broken test to ignore).
3. As Priority-1 gaps close (see [`../14-project-management/43-product-roadmap.md`](../14-project-management/43-product-roadmap.md) recommended sequencing), the E2E test should flip green stage by stage, giving continuous, objective confirmation of progress — a much stronger signal than "the ticket says it's done."
4. Add Scenario B–D (cancellation, KYC rejection, payment failure) once the happy path passes.

## Chaos/resilience testing

Fault injection (Redis down, DB locked, third-party timeouts) — explicitly planned in `docs/MASTER_PLAN.md` §8, not yet built. This is a distinct, later-stage investment from the happy-path E2E suite above and should follow it, not precede it.

## Related documents

[`143-test-strategy.md`](143-test-strategy.md), [`146-integration-testing.md`](146-integration-testing.md), [`31-test-case-repository.md`](31-test-case-repository.md), [`../14-project-management/43-product-roadmap.md`](../14-project-management/43-product-roadmap.md).
