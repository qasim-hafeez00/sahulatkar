# Idempotency Standards

**Status:** STABLE — expanded from [`23-api-standards.md`](23-api-standards.md), since idempotency deserves standalone treatment given how many financial-correctness gaps trace back to it.

## The standard

Every state-changing financial endpoint should accept a client-supplied idempotency key, check for a prior identical request in the application layer *before* attempting a write, and return the original response unchanged on a repeat — never a second side effect, never a raw database error.

## Current reality

Idempotency is enforced only via database-level uniqueness constraints (e.g., `PaymentWorkflow.idempotency_key`, `payment_transactions.gateway_txn_id UNIQUE`) — with no application-layer pre-check. A concurrent duplicate request surfaces as a 500 (constraint violation) rather than a clean 200 with the original result (`PO-BL-06`).

## Why this specific gap matters more than it might seem

A raw 500 on a duplicate financial request is worse than just an ugly error — client-side retry logic (mobile networks drop, a customer double-taps "pay") is exactly the scenario idempotency exists to protect against, and the current behavior actively punishes the retry instead of absorbing it gracefully. This directly connects to the webhook-deduplication gap (`GW-BL-13`) — both are the same underlying missing capability (application-layer idempotency) showing up in two different code paths.

## Recommended pattern

```
1. Client sends request with Idempotency-Key header
2. Server checks: has this key been seen before?
   - Yes, and the prior request succeeded → return the cached/original response, no new write
   - Yes, and the prior request is still in-flight → return 409 or wait/retry guidance
   - No → proceed with the write, record the key against the result
```

This should live in `sk_shared` as a reusable decorator/middleware, not be reimplemented per-service — mirroring the same duplication-avoidance recommendation made elsewhere in this knowledge base for HMAC verification and pagination.

## Related documents

[`23-api-standards.md`](23-api-standards.md), [`../09-qa/32-financial-transaction-test-strategy.md`](../09-qa/32-financial-transaction-test-strategy.md) (concurrency test cases for this exact gap).
