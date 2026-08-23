# QA Strategy

**Status:** STABLE (policy, from `docs/MASTER_PLAN.md` §12) — actual current coverage not independently re-verified in this pass; see gaps below.

## Test pyramid

```
                ┌─────────┐
                │  E2E    │  5%  — Playwright browser tests
               ┌┴─────────┴┐
               │Integration │ 25% — API tests with real DB + Redis
              ┌┴───────────┴┐
              │  Unit Tests  │ 70% — pure function, mocked I/O
              └──────────────┘
```

## Required tests per service, before merge

| Test type | Tool | Minimum bar |
|---|---|---|
| Unit | pytest | 80% line coverage |
| Integration | pytest + testcontainers | All API endpoints |
| Lint | ruff | Zero violations |
| Type check | mypy | No errors (`--ignore-missing-imports`) |
| Security | bandit | No high-severity findings |
| Frontend unit | vitest | 70% coverage |
| Frontend E2E | Playwright | Critical paths |

Enforced in CI: `.github/workflows/ci.yml` runs lint → unit test (matrix across all 6 backend services + 2 frontends, with real Postgres/Redis service containers) → migration reversibility check → the hard-gate test specifically → Docker build verification.

## Critical path tests — NEVER marked `xfail`, never skipped

These five are explicitly called out in `docs/MASTER_PLAN.md` as tests that must always run and always pass in CI:

1. `test_murabaha_hard_gate` — VCN issuance is blocked without a signed contract.
2. `test_late_fee_charity` — 100% of late fees route to charity.
3. `test_prohibited_category_block` — alcohol/tobacco/gambling/etc. are blocked before an offer is generated.
4. `test_cost_price_disclosure` — the Murabaha contract has all 3 mandatory disclosure fields populated.
5. `test_credit_sla` — the credit check completes in under 3 seconds.

## What's actually true today vs. the policy above

The policy is clear and CI is wired to enforce it, but the 2026-04-27 code audit (`docs/PRODUCTION_GAPS_REPORT.md`) found substantial functional gaps *underneath* passing tests — meaning "tests pass" and "the feature works end-to-end" are not currently the same claim for this codebase. Two concrete examples: the scraping worker crash (`PS-BUG-01`) and the incomplete checkout form-filler (`PS-BL-03`) are both in code paths that presumably have some unit test coverage per the 80% policy, yet neither works when actually exercised end-to-end. This suggests either (a) integration/E2E coverage of the full 12-step flow is thinner than the unit-test percentage implies, or (b) tests exist but don't exercise the failing code paths. **Recommend an explicit end-to-end integration suite covering the full 12-step flow** (referenced as a Phase 4 target in `docs/MASTER_PLAN.md` §8 but not yet built) as the highest-leverage QA investment right now — see [`31-test-case-repository.md`](31-test-case-repository.md).

## Chaos / resilience testing (Phase 4 target, not yet built)

Fault injection (Redis down, DB locked, third-party timeouts) to verify circuit breakers and dead-letter queues actually work — explicitly planned but not yet implemented per `docs/MASTER_PLAN.md` §8.

## Load testing (Phase 4 target, not yet built)

k6 scripts targeting 1,000 concurrent users — planned, not yet built.

## UAT process

Not documented in current engineering docs beyond the general release-checklist items in `docs/MASTER_PLAN.md` §13 (pre-push checklist). Recommend Product/QA define a formal UAT sign-off process ahead of any real-money launch.

## Related documents

[`31-test-case-repository.md`](31-test-case-repository.md), [`32-financial-transaction-test-strategy.md`](32-financial-transaction-test-strategy.md), `docs/PRODUCTION_GAPS_REPORT.md`.
