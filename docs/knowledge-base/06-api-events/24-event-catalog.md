# Event Catalog

**Status:** STABLE — mechanism confirmed (Redis Pub/Sub); catalog includes both working and confirmed-missing events, clearly marked.

## Mechanism

Redis Pub/Sub for real-time cross-service state synchronization; Redis-backed queues (BullMQ) for durable background task execution. No schema-enforced event envelope exists yet — `build_event_envelope()` in `sk_shared` builds the JSON metadata wrapper but does not validate payload shape against a Pydantic model, so a service can publish a malformed event without being stopped (`SH-GAP-03`).

## Working events (published and consumed, per source docs and audit)

| Event | Published by | Consumed by | Payload (key fields) |
|---|---|---|---|
| `product.extracted` | Product Service | Gateway | `order_id`, `upo: { product_id, title, price_pkr, canonical_url, selected_variant, availability }` |
| `payment.down_payment_confirmed` | Payment Orchestrator | Product Service (triggers VCN issuance chain) | `order_id`, `installment_id`, `amount_pkr`, `vcn_id`, `vcn_pan`, `vcn_expiry`, `vcn_cvv` |
| `vcn.issued` | Payment Orchestrator | Product Service (triggers checkout queue) | VCN details, `order_id` |
| `order.purchase_confirmed` | Product Service (checkout agent) | Gateway, Notification Service | `order_id`, `merchant_order_id`, `total_charged_pkr`, `confirmation_screenshot_s3`, `timestamp` |
| `delivery_status_changed`, `delivery_confirmed` | Notification Service (AfterShip webhook) | Gateway (delivery event listener) | shipment status, `order_id` |
| `payment.confirmed` | Payment Orchestrator | Ledger Service (posts GL entry) | payment amount, `installment_id` — **known gap:** the handler does not validate this amount against the loan's actual installment amount before posting (`LS-BL-05`) |

## Confirmed-missing events (referenced by a consumer, never published by any producer)

These are structural gaps, not just missing features — a consumer service has code written to listen for these, and no producer service emits them, per the 2026-04-27 code audit:

| Missing event | Should be published by | Should be consumed by | Real-world impact |
|---|---|---|---|
| `loan.created` | Gateway (on Murabaha signing) | Ledger Service | **Highest-severity gap in the platform.** No initial liability/receivable journal entries are ever posted for any loan. |
| `billing.installment_overdue` | Ledger `BillingSweepWorker` | Notification Service | Customers get pre-due reminders (D-3, D-1) but no notice once actually overdue. |
| `order.cancelled` | Gateway | Notification Service, Payment Orchestrator | No cancellation notification sent; VCN not voided on cancellation. |
| `vcn.expired` | Payment Orchestrator | Notification Service | No customer notification when a VCN expires. |
| `payment.failed` (auto-debit) | Payment Orchestrator | Notification Service | No notification on failed automatic installment collection. |
| `kyc.documents_needed` | Gateway | Notification Service | No prompt to resubmit KYC documents. |
| `credit.limit_changed` | Gateway | Notification Service | No notification when a credit limit changes. |

## Internal REST callbacks (not pub/sub, but functionally event-like)

Several "events" in this system are actually direct HTTP callbacks rather than durable pub/sub messages — worth documenting as a distinct pattern with a distinct risk profile (no retry/timeout if the receiver is down):

- `POST /v1/internal/orders/{order_id}/product-extracted` and `.../extraction-failed` (Product Service → Gateway) — **known gap:** no retry or timeout if Gateway is unreachable; an order can stay stuck in `url_received` indefinitely.
- `POST /v1/internal/payments/{payment_id}/confirm` (Payment Orchestrator → Gateway) — the uncompensated-transaction gap referenced throughout this knowledge base.
- `POST /v1/internal/users/{user_id}/credit-result` (Credit Engine → Gateway).
- `POST /v1/internal/orders/{order_id}/checkout-status` (Product Service → Gateway).

## Retry / dead-letter strategy

DLQ pattern exists but is fragmented — at least 4 separate DLQ systems (scraping, checkout, notification, ledger events) with **no unified monitoring or alerting**, and the Ledger Service's event DLQ specifically has no consumer at all — failed events accumulate forever (`LS-CRIT-05`, `INF-GAP-05`).

## Idempotency

Not enforced at the event-envelope level (see Mechanism above). Idempotency for financial events currently relies on downstream DB uniqueness constraints (e.g. `gateway_txn_id UNIQUE` on `payment_transactions`) rather than event-level deduplication.

## Ordering

No documented ordering guarantee exists for Redis Pub/Sub in this system — events are effectively best-effort, at-most-once for pub/sub subscribers who aren't actively listening at publish time. Anything requiring guaranteed delivery uses a queue (BullMQ) instead, which is the correct pattern, but not universally applied (e.g. the internal-callback pattern above has neither guarantee).

## Related documents

[`23-api-standards.md`](23-api-standards.md), [`../02-business-workflows/07-bnpl-workflow-e2e.md`](../02-business-workflows/07-bnpl-workflow-e2e.md), [`../05-architecture/21-service-responsibility-matrix.md`](../05-architecture/21-service-responsibility-matrix.md).
