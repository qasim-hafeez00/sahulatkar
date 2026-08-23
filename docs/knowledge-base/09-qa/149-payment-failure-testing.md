# Payment Failure Testing

**Status:** STABLE (strategy)

## What to test

Every row in [`../19-payments-financial-operations/103-failed-payment-handling.md`](../19-payments-financial-operations/103-failed-payment-handling.md)'s failure-moment table: down-payment decline, installment auto-collection failure (once implemented), VCN issuance failure, and the retryable-vs-non-retryable classification (`PO-BL-02`) once it exists.

## Gateway-specific failure simulation

Each gateway adapter (Safepay, JazzCash, EasyPaisa) should have tests simulating: a timeout (should be treated as retryable), an explicit decline response (should be treated as non-retryable and surfaced to the customer immediately), a malformed/unexpected response shape (should fail gracefully, not crash the adapter), and a webhook that never arrives (should the order/payment time out and prompt a retry, or hang indefinitely? — currently undocumented behavior per [`../02-business-workflows/08-payment-workflow.md`](../02-business-workflows/08-payment-workflow.md), and exactly the kind of ambiguity a test would force to be resolved).

## Duplicate webhook testing

Directly targets `GW-BL-13` — send the same webhook payload twice, assert the payment is only confirmed once and no duplicate journal entry results. This is both a payment-failure-handling test and a ledger-invariant test simultaneously (see [`148-ledger-testing.md`](148-ledger-testing.md)) — worth having in both suites given how directly it connects the two domains.

## Related documents

[`../19-payments-financial-operations/103-failed-payment-handling.md`](../19-payments-financial-operations/103-failed-payment-handling.md), [`../19-payments-financial-operations/105-payment-retry-rules.md`](../19-payments-financial-operations/105-payment-retry-rules.md), [`32-financial-transaction-test-strategy.md`](32-financial-transaction-test-strategy.md).
