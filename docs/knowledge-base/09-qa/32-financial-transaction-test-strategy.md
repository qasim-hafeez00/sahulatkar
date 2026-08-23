# Financial Transaction Test Strategy

**Status:** STABLE (strategy) — built around the specific financial-correctness gaps the code audit surfaced, since those are exactly the class of bug generic functional testing tends to miss.

## Why this needs its own strategy, separate from general QA

Financial transaction bugs frequently pass ordinary functional tests (the API returns 200, the UI shows success) while silently corrupting the books, double-charging a customer, or losing money. The 2026-04-27 code audit found several bugs in exactly this shape — code that "works" from a request/response perspective but is financially wrong. This strategy targets that specific failure class.

## Core invariants to test explicitly (not just implicitly via feature tests)

| Invariant | Why it matters | Current status |
|---|---|---|
| Every `journal_entries` row has `total_debit == total_credit` | The fundamental double-entry accounting rule | **Currently NOT validated in code** (`LS-CRIT-02`) — this should be the #1 new test written, both as a DB-level constraint and an application-level assertion before any entry is committed |
| Every signed Murabaha contract eventually has corresponding GL entries | Otherwise the ledger silently omits real loans | **Currently fails for every loan** — no service publishes `loan.created` |
| `available_credit` is correctly decremented at order initiation and restored (only) on legitimate cancellation | Prevents credit-limit double-spend and prevents restoring credit that was never actually reserved | **Currently broken both directions** (`GW-BL-01`) |
| Late fees collected always equal late fees disbursed to charity | Core Shariah-compliance invariant, not just accounting hygiene | **Currently untested and unimplemented** — charity disbursement is a stub (`LS-CRIT-03`) |
| A payment gateway's reported settlement amount matches SahulatKar's internal `payment_transactions` record, per transaction | Detects silent money leakage or double-processing | **Currently reconciliation runs against mock data, not live gateway data** (`PO-CRIT-02`) |
| A given idempotency key never results in two distinct financial side effects | Prevents duplicate charges/webhook replays from double-processing | **Currently enforced only at the DB-constraint layer, surfacing as a 500 rather than a clean idempotent response** (`PO-BL-06`) |
| VCN spend never exceeds `authorized_amount` (cost + 5% buffer) | Prevents runaway/fraudulent charges through the automated checkout agent | Enforced by issuer-side spend controls (MCC lock, amount cap) — verify this is independently tested against the actual Stripe Issuing configuration, not just asserted in application code |

## Concurrency-specific test cases

Financial bugs are disproportionately concurrency bugs. Explicitly test:

- Two simultaneous order-initiation requests from the same user, each within the user's credit limit individually but exceeding it combined — should not both succeed once `GW-BL-01` is fixed.
- Two simultaneous webhook deliveries for the same gateway transaction (duplicate delivery) — should not double-confirm the payment once deduplication is added (`GW-BL-13`).
- Concurrent requests using the same idempotency key — should return the identical original response, not a 500 or a second charge.

## Exact-decimal assertion discipline

Every monetary assertion in tests should compare `Decimal` values exactly (matching the platform's `DECIMAL(14,2)` DB rule) — never compare via float equality or an approximate tolerance, since float rounding errors are exactly the class of bug the platform's own "never use FLOAT" rule exists to prevent. Test authors should treat a float appearing anywhere in a financial test as a bug in the test itself.

## Reconciliation test strategy (once `PO-CRIT-02` is fixed)

Once real gateway settlement data is wired in, tests should cover: exact match (happy path), amount-mismatch flagging, missing-settlement flagging (SahulatKar recorded a payment the gateway never confirms), and missing-internal-record flagging (gateway settled something SahulatKar has no record of) — the last two are the cases most likely to indicate a real financial problem (fraud, integration bug, or lost revenue) rather than routine timing drift.

## Shariah-compliance-relevant financial tests

Cross-reference with [`../04-shariah/17-shariah-product-structure.md`](../04-shariah/17-shariah-product-structure.md): `test_late_fee_charity` and `test_cost_price_disclosure` (both already listed as never-`xfail` critical-path tests in [`30-qa-strategy.md`](30-qa-strategy.md)) belong in this category too — they are simultaneously financial-correctness tests and Shariah-compliance tests, and should be owned jointly by QA and whoever is accountable for Shariah compliance sign-off.

## Related documents

[`30-qa-strategy.md`](30-qa-strategy.md), [`31-test-case-repository.md`](31-test-case-repository.md), [`../07-database/25-database-architecture.md`](../07-database/25-database-architecture.md) (monetary field rules).
