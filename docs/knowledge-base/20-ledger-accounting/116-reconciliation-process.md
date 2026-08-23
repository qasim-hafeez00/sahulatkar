# Reconciliation Process (Ledger-Side)

**Status:** STABLE — distinct from [`../19-payments-financial-operations/102-payment-reconciliation.md`](../19-payments-financial-operations/102-payment-reconciliation.md) (which covers gateway-settlement matching); this document covers the **ledger's own internal reconciliation** — confirming the ledger agrees with the systems that fed it.

## What this reconciliation checks

Not "did the gateway settle what we expect" (that's payment reconciliation) but "does the ledger's recorded revenue/receivables actually match the source transaction records in Payment Orchestrator and the loan records in Gateway." These are two different reconciliation problems that happen to use a similar word — this document exists to keep them distinct.

## Known gap

**Ledger-side reconciliation currently only checks that revenue *was posted at all* for a given period — not that the *amount* posted matches the corresponding `PaymentTransaction` record** (`LS-BL-06`). This means the current reconciliation check would pass even if, say, a payment of PKR 5,000 was incorrectly posted to the ledger as PKR 500 — as long as *some* revenue entry exists, the check is satisfied. This is a materially weaker check than what "reconciliation" normally implies, and should be strengthened to an amount-level match, not just a presence check.

## What a complete ledger reconciliation should verify

1. Every `payment_transactions` row with `status='success'` has a corresponding journal entry.
2. The journal entry's amount matches the payment transaction's amount exactly (to the paisa).
3. Every signed Murabaha contract (`murabaha_contracts` with `signed_at` populated) has corresponding initial liability/receivable entries — currently fails for 100% of contracts due to the missing `loan.created` event.
4. No orphaned journal entries exist with a `source_id` that doesn't resolve to a real record in the source service.

## Related documents

[`../19-payments-financial-operations/102-payment-reconciliation.md`](../19-payments-financial-operations/102-payment-reconciliation.md), [`113-ledger-invariants.md`](113-ledger-invariants.md), [`../09-qa/32-financial-transaction-test-strategy.md`](../09-qa/32-financial-transaction-test-strategy.md).
