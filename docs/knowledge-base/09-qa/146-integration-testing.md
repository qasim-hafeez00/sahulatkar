# Integration Testing

**Status:** STABLE (policy) — the cross-service integration points this strategy should specifically target are enumerated in [`31-test-case-repository.md`](31-test-case-repository.md); this document covers the strategic framing.

## Scope

Per the test pyramid in [`30-qa-strategy.md`](30-qa-strategy.md), integration tests target ~25% of total test volume: API tests against a real database and Redis (via testcontainers), run per-service in CI.

## Where integration testing needs to extend beyond single-service scope

The current CI structure runs integration tests **per service in isolation** (per the CI pipeline matrix in [`../10-devops/34-deployment-process.md`](../10-devops/34-deployment-process.md)) — this catches bugs within a service's own API/DB/Redis interaction, but **cannot catch the cross-service event gaps that are the platform's most severe known issues** (missing `loan.created`, missing `billing.installment_overdue`, etc.), since those require exercising two services together with a real event bus between them.

## Recommended addition: cross-service integration harness

A test environment that spins up multiple services together (or at minimum, the two services on each side of a critical event) with a real Redis instance, publishes an event from the source service, and asserts the consuming service reacted correctly — this is a materially different (and currently missing) test tier from both single-service integration tests and full end-to-end tests (see [`147-end-to-end-testing.md`](147-end-to-end-testing.md)). Every row in [`../06-api-events/127-event-ownership.md`](../06-api-events/127-event-ownership.md)'s "confirmed-missing" section is a candidate for exactly this kind of test — the test would currently fail (correctly), documenting the gap, and flip to passing once the event is actually published.

## Related documents

[`143-test-strategy.md`](143-test-strategy.md), [`../06-api-events/127-event-ownership.md`](../06-api-events/127-event-ownership.md), [`147-end-to-end-testing.md`](147-end-to-end-testing.md).
