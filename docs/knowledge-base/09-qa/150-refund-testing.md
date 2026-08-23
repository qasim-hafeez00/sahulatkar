# Refund Testing

**Status:** PLANNED — cannot currently be tested, since there is nothing to test. This document specifies what will be needed once `RefundOrchestrator` is built.

## Why this document exists despite the feature not existing

Writing the test strategy before the feature is complete (rather than after) means the acceptance criteria for "refunds work correctly" are defined independently of whatever the initial implementation happens to do — a useful discipline given how much of this platform's current gap inventory consists of features that technically "exist" (an endpoint returns something) without actually being correct.

## Required test coverage once `RefundOrchestrator` is implemented

- Each scenario in [`../19-payments-financial-operations/106-refund-rules.md`](../19-payments-financial-operations/106-refund-rules.md)'s proposed rules table: cancellation-before-payment (no refund needed), cancellation-after-down-payment (full refund), purchase-failure refund, merchant-accepted-return refund.
- Refund routes to the **original payment method**, not a different one, and for the **original amount** (or the correctly adjusted partial amount for a partial return).
- The corresponding ledger `refund` entry is posted and correctly offsets the original revenue recognition — see [`../20-ledger-accounting/112-transaction-types.md`](../20-ledger-accounting/112-transaction-types.md).
- VCN void is triggered where applicable (a refund on a cancelled order should void any still-active VCN, not leave it live).
- Idempotency: a duplicate refund request for the same order does not issue two refunds.

## Related documents

[`../02-business-workflows/09-refund-cancellation-workflow.md`](../02-business-workflows/09-refund-cancellation-workflow.md), [`../19-payments-financial-operations/106-refund-rules.md`](../19-payments-financial-operations/106-refund-rules.md).
