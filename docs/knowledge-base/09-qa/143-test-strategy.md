# Test Strategy

**Status:** STABLE — the overarching strategy document; [`30-qa-strategy.md`](30-qa-strategy.md) covers the specific pyramid/coverage-bar policy this document sits above.

## Relationship to QA Strategy

Where [`30-qa-strategy.md`](30-qa-strategy.md) answers "what's our testing policy" (pyramid shape, coverage bars, critical-path tests), this document answers "how do we decide what to test and to what depth" — the strategic layer above the tactical one.

## Risk-based prioritization principle

Test depth should scale with financial/compliance/Shariah consequence, not with code complexity alone. This is why [`32-financial-transaction-test-strategy.md`](32-financial-transaction-test-strategy.md) exists as its own document rather than being folded into general functional testing — the consequence of a financial-correctness bug (silently wrong money) is categorically worse than a UI bug, and testing effort should reflect that asymmetry explicitly.

## The strategy's central finding, restated

The 2026-04-27 code audit demonstrated that "tests pass" and "the platform works end-to-end" are currently different claims for this codebase (see [`30-qa-strategy.md`](30-qa-strategy.md)) — this is the single most important strategic input for QA leadership: **prioritize closing the gap between unit-test coverage and true end-to-end functional coverage** over increasing unit-test percentage further, since the former is where the platform's actual risk currently concentrates.

## Test category index

[`31-test-case-repository.md`](31-test-case-repository.md) (scenarios), [`144-api-testing-strategy.md`](144-api-testing-strategy.md), [`145-ui-testing-strategy.md`](145-ui-testing-strategy.md), [`146-integration-testing.md`](146-integration-testing.md), [`147-end-to-end-testing.md`](147-end-to-end-testing.md), [`32-financial-transaction-test-strategy.md`](32-financial-transaction-test-strategy.md), [`148-ledger-testing.md`](148-ledger-testing.md), [`149-payment-failure-testing.md`](149-payment-failure-testing.md), [`150-refund-testing.md`](150-refund-testing.md), [`151-fraud-testing.md`](151-fraud-testing.md), [`152-security-testing.md`](152-security-testing.md), [`153-performance-testing.md`](153-performance-testing.md).

## Related documents

[`30-qa-strategy.md`](30-qa-strategy.md), [`154-uat-process.md`](154-uat-process.md), [`155-release-acceptance-criteria.md`](155-release-acceptance-criteria.md).
