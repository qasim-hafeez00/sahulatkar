# Payment Orchestrator

**Status:** STABLE (design) — ~70% complete per audit, blocked by refund and reconciliation gaps.

## Purpose

Owns the "collect first, then buy" payment sequence: down payment collection, VCN issuance, installment collection, gateway-settlement reconciliation.

## Responsibilities

- Down payment and installment collection via Safepay, JazzCash, EasyPaisa (Raast planned).
- VCN lifecycle: issue (only after `contracts_signed`), void, status, decrypt (internal, for the checkout agent).
- Gateway adapters and webhook handling (HMAC-verified).
- Payment-gateway settlement reconciliation — see [`../../02-business-workflows/11-merchant-settlement-reconciliation.md`](../../02-business-workflows/11-merchant-settlement-reconciliation.md).
- Refunds — designed but not implemented, see below.

## Dependencies

Stripe Issuing (VCN, MVP), Safepay, JazzCash, EasyPaisa, PostgreSQL, Redis (idempotency, rate limiting), Gateway (order-status callbacks).

## Key APIs

`POST /payments/down-payment`, `POST /payments/pay-installment`, `POST /payments/refund` (stub), `POST /vcn/issue`, `POST /vcn/void`, `GET /vcn/{order_id}/status`, `POST /vcn/{order_id}/decrypt` (internal). Full spec: `docs/System-md-files/M06-M09-payments-vcn-agent-hitl.md` (M06, M07 sections).

## Events

Publishes `payment.down_payment_confirmed`, `vcn.issued`. Should consume `order.cancelled` to void an active VCN — **no handler currently exists for this** (a cross-service gap noted in `docs/PRODUCTION_GAPS_REPORT.md` §12.2).

## Database ownership

`loans`, `installments`, `payment_transactions`, `virtual_cards`.

## Known gaps (from `docs/PRODUCTION_GAPS_REPORT.md` §4)

- **PO-CRIT-01 (critical):** `RefundOrchestrator.initiate_refund()` is a stub — there is no working refund pathway anywhere in the system. See [`../../02-business-workflows/09-refund-cancellation-workflow.md`](../../02-business-workflows/09-refund-cancellation-workflow.md).
- **PO-CRIT-02 (critical):** settlement reconciliation reads mock local JSON files, not real gateway SFTP/API data — financial reconciliation does not function against live data.
- **PO-CRIT-04 (high):** VCNs marked locally expired are not actually voided on Stripe — up to 24 hours of extra exposure.
- **PO-CRIT-05 (high):** Stripe webhook events (e.g. `issuing_card.updated`) have no receiving endpoint in this service — the poller alone can't substitute for real-time webhook handling.
- **PO-BL-01 (high):** the internal VCN-decrypt endpoint has no rate limiting.
- Full checklist: `docs/PRODUCTION_GAPS_REPORT.md` §4, §13.

## Security note

VCN PAN/CVV are AES-256 encrypted at rest and must never appear in application logs (platform-wide immutable rule, see [`../../08-security/27-security-architecture.md`](../../08-security/27-security-architecture.md)).
