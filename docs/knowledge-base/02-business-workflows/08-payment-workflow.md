# Payment Workflow

**Status:** STABLE (target design) — gaps flagged inline.

## Principle: Collect First, Then Buy

```
1. Order status = 'contracts_signed'
2. Present payment screen (amount, methods)
3. User pays down payment via Safepay / JazzCash / EasyPaisa
4. Webhook confirms payment → mark installment[0] PAID
5. Publish 'payment.down_payment_confirmed'
6. VCN Service issues VCN
7. Checkout Agent executes purchase
```

The purchase (step 7) never runs ahead of confirmed payment (step 4). VCN issuance never runs ahead of contract signing, independent of payment status (see the hard gate in [`07-bnpl-workflow-e2e.md`](07-bnpl-workflow-e2e.md)).

## Payment methods (priority order)

| Method | Reach | Fee | Settlement | Flow |
|---|---|---|---|---|
| Safepay (cards + wallets) | Universal | 2.9% + PKR 30 | T+2 | Async redirect (user leaves app, pays, returns) |
| JazzCash Direct API | 40M+ wallets | 1.5–2% | T+1 | Synchronous |
| EasyPaisa Direct API | 35M+ wallets | 1.5–2% | T+1 | Synchronous |
| Raast | SBP instant rail | ~0% | T+0 | **Phase 4 — not yet live** (mandate lookup for recurring auto-debit is referenced in code but not implemented, per audit PO-CRIT-03) |

Operator detection: after 4 digits of a phone number, the UI shows the Jazz/Telenor/Zong/Ufone badge and only offers methods valid for that operator.

## Down payment

25–40% of order value depending on credit band (see [`../03-bnpl-financing/15-credit-limit-rules.md`](../03-bnpl-financing/15-credit-limit-rules.md)). `POST /payments/down-payment` creates a `payment_transactions` record and either returns a Safepay redirect URL or a direct JazzCash/EasyPaisa charge result. Webhook (`POST /webhooks/safepay`, `POST /webhooks/jazzcash`), HMAC-signature-verified, confirms success and triggers the VCN issuance chain.

**Known gap:** webhook handlers validate HMAC and enqueue to Redis but do not currently deduplicate — a duplicate webhook delivery can double-confirm a payment (GW-BL-13).

## Installment collection

Daily billing sweep (`pg_cron`, 08:00) scans `installments WHERE status='pending' AND due_date <= CURRENT_DATE` using a critical partial index (`(due_date, user_id) WHERE status='pending'`, sized to process 100K rows in <60s). Retry schedule on failure:

| Attempt | Timing |
|---|---|
| 1 (due date) | 9:00 AM |
| 2 (same day) | 6:00 PM |
| 3 (next day) | 9:00 AM |
| 4 (day+2) | 12:00 PM |
| After 4 fails | Flagged for manual collections outreach — see [`10-default-collections-workflow.md`](10-default-collections-workflow.md) |

**Known gap (LS-CRIT-04, PO-EP-06):** the sweep correctly identifies due/overdue installments but has no implemented call into Payment Orchestrator to actually attempt the charge — `/api/internal/installments/{id}/auto-collect` does not exist yet. Auto-collection is not automatic in the current build; installment payment is currently customer-initiated only (`POST /api/v1/payments/installment/{id}/pay`).

## Manual payment recording

`POST /payments/manual-record` (admin, `finance_analyst` role) — for bank deposits or office cash payments, generates a receipt to the customer.

## Reconciliation

See [`11-merchant-settlement-reconciliation.md`](11-merchant-settlement-reconciliation.md) for gateway-settlement reconciliation (distinct from merchant settlement, which doesn't apply to this model).

## Failure cases

| Failure | Handling |
|---|---|
| Down payment fails | Order remains at `contracts_signed`; customer can retry from the payment screen |
| Webhook never arrives | **Gap:** no documented timeout/retry mechanism for a missing webhook — order can stall indefinitely |
| VCN issuance fails (issuer down) | **Gap (PO-CRIT-04 family):** order status does not roll back; no admin retry endpoint exists yet |
| Installment charge fails after all retries | Flagged for manual collections outreach; TASDEEQ negative reporting begins per the escalation timeline |
| Duplicate webhook delivery | **Gap (GW-BL-13):** can double-confirm a payment — no deduplication currently |

## Related documents

[`07-bnpl-workflow-e2e.md`](07-bnpl-workflow-e2e.md), [`10-default-collections-workflow.md`](10-default-collections-workflow.md), [`../05-architecture/microservices/payment-orchestrator.md`](../05-architecture/microservices/payment-orchestrator.md).
