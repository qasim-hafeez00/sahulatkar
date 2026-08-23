# Payment Lifecycle

**Status:** STABLE — the `payment_transactions.status` state machine, standalone since it's referenced from multiple other documents but not previously given its own home.

## States

```
initiated → pending → success
                    → failed → (retry: new transaction, retry_of_txn_id links back)
          → refunded    [target design — not yet implemented, RefundOrchestrator is a stub]
          → chargeback  [target design — no chargeback handling implemented, see business-workflows/54]
```

## Transition triggers

| Transition | Trigger |
|---|---|
| `initiated` → `pending` | Gateway API call made, awaiting response/webhook |
| `pending` → `success` | Webhook confirms payment (HMAC-verified) or synchronous gateway response is success |
| `pending` → `failed` | Webhook reports failure, or gateway times out |
| `failed` → new `initiated` (retry) | Customer or automated retry initiates a new attempt, linked via `retry_of_txn_id` |
| `success` → `refunded` | **Not implemented** — see [`../02-business-workflows/09-refund-cancellation-workflow.md`](../02-business-workflows/09-refund-cancellation-workflow.md) |
| `success` → `chargeback` | **Not implemented** — see [`../02-business-workflows/54-chargeback-dispute-workflow.md`](../02-business-workflows/54-chargeback-dispute-workflow.md) |

## Retryable vs. non-retryable failure

**Known gap:** gateway adapters currently don't differentiate a retryable failure (network timeout — worth retrying) from a non-retryable one (invalid card, insufficient funds — retrying won't help) — all failures increment `attempt_count` identically (`PO-BL-02`). This matters for the retry schedule described in [`../02-business-workflows/08-payment-workflow.md`](../02-business-workflows/08-payment-workflow.md): retrying a non-retryable failure four times per the schedule wastes cycles and delays the point at which a customer or collections staff learns the real underlying problem (e.g., "your card was declined," not "we'll try again in a few hours").

## Idempotency across the lifecycle

`gateway_txn_id` is unique-indexed for fast webhook lookup and natural deduplication at the database layer — but as noted in [`../06-api-events/23-api-standards.md`](../06-api-events/23-api-standards.md), this currently surfaces as a raw constraint-violation error rather than a clean idempotent response when a duplicate is attempted.

## Related documents

[`99-payment-architecture.md`](99-payment-architecture.md), [`../02-business-workflows/08-payment-workflow.md`](../02-business-workflows/08-payment-workflow.md), [`103-failed-payment-handling.md`](103-failed-payment-handling.md).
