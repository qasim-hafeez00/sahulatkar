# Ledger Testing

**Status:** STABLE (strategy) — directly maps to [`../20-ledger-accounting/113-ledger-invariants.md`](../20-ledger-accounting/113-ledger-invariants.md)'s invariant list.

## What ledger testing must verify

Every row in [`../20-ledger-accounting/113-ledger-invariants.md`](../20-ledger-accounting/113-ledger-invariants.md) is a required test case: debit=credit on every entry, immutability of posted entries, balances always derived (never directly written), a `loan.created` event resulting in correct initial entries, late-fee-collected equals late-fee-disbursed, closed periods reject backdated entries, and invalid account codes are rejected cleanly rather than causing a raw DB error.

## Testing approach for the debit=credit invariant specifically

This should be tested at two levels: (1) a unit test on the entry-construction code confirming it refuses to build an unbalanced entry, and (2) a database-level constraint (a `CHECK` or trigger enforcing `total_debit = total_credit`) as a second, independent line of defense — relying on application-code discipline alone is exactly the pattern that led to `LS-CRIT-02` existing as a gap in the first place.

## Testing the missing `loan.created` chain

Once fixed, this needs an integration test (see [`146-integration-testing.md`](146-integration-testing.md)) that signs a Murabaha contract, confirms the event publishes, confirms Ledger Service consumes it, and confirms the resulting journal entries exactly match the expected liability/receivable/revenue split — not just "an entry was created," but the correct entry.

## Financial statement testing

Once the cash-flow-statement stub (`LS-CRIT-01`) is implemented, it needs test coverage verifying it reconciles against the trial balance for the same period — a cash flow statement that doesn't tie out to the balance sheet/income statement is worse than no statement, since it would look authoritative while being wrong.

## Related documents

[`../20-ledger-accounting/113-ledger-invariants.md`](../20-ledger-accounting/113-ledger-invariants.md), [`32-financial-transaction-test-strategy.md`](32-financial-transaction-test-strategy.md), [`../20-ledger-accounting/117-financial-reporting.md`](../20-ledger-accounting/117-financial-reporting.md).
