# End-to-End BNPL Workflow

**Status:** STABLE (target design, system-internal view). This is the systems/services counterpart to [`05-customer-journey-e2e.md`](05-customer-journey-e2e.md) — same flow, described in terms of triggers, services, events, and failure modes rather than the customer-facing screens.

## Trigger

Customer submits `POST /products/extract` with a raw URL (Gateway → Product Service).

## Actors

Customer, Gateway (BFF), Product Service, Credit Engine, Payment Orchestrator, Ledger Service, Notification Service, Playwright checkout agent, HITL operator (conditional).

## Preconditions

User authenticated (valid JWT), `users.status = 'active'` (i.e. KYC already approved).

## Steps, services, and events

| # | Step | Primary service | Event published | DB changes |
|---|---|---|---|---|
| 1 | URL submitted, order created | Gateway → Product Service | — | `orders` row created, status `url_submitted` |
| 2 | Merchant page scraped | Product Service (`ScrapingWorker`) | — | `scraping_jobs` row |
| 3 | UPO extracted (GPT-4o Vision fallback) | Product Service | `product.extracted` | `products` row |
| 4 | Credit assessed (<3s) | Credit Engine | — | `credit_applications`, `risk_assessments` |
| 5 | Offer presented | Product Service (pricing) → Gateway | — | order status → `offer_presented` |
| 6 | Wakalah signed (OTP) | Gateway (`contract_generator`, `contract_signer`) | — | `wakalah_agreements`, `contract_digital_signatures` |
| 7 | Murabaha signed (OTP) — **HARD GATE** | Gateway | *(should be `loan.created` — currently not published, see Known Cross-Service Gap below)* | `murabaha_contracts`, `loans`; order status → `contracts_signed` |
| 8 | Down payment collected | Payment Orchestrator | `payment.down_payment_confirmed` | `payment_transactions`, `installments[0]` → paid |
| 9 | VCN issued | Payment Orchestrator (`vcn.py`) | `vcn.issued` | `virtual_cards` row |
| 10 | Checkout executed | Product Service (`CheckoutConsumer`, Playwright) | `order.purchase_confirmed` or `checkout-status: failed` | `purchase_executions` row |
| 11 | Delivery tracked | Notification Service (AfterShip webhook) | `delivery_status_changed`, `delivery_confirmed` | `shipments`, `tracking_events` |
| 12 | Installments collected | Ledger Service (`BillingSweepWorker`) → Payment Orchestrator | *(should trigger auto-collect — currently not wired, see below)* | `installments` status updates, `journal_entries` |

## Business rules

- **Hard gate (immutable):** VCN issuance requires `order.status == 'contracts_signed'`. Gateway middleware returns HTTP 403 `MURABAHA_NOT_SIGNED` otherwise. This is tested in CI on every push and must never be skipped.
- **Collect first, then buy:** the down payment must be confirmed before a VCN is ever issued; a purchase is never executed on unconfirmed funds.
- **Prohibited-category block:** enforced before any offer is generated (step 3–5), not just at checkout.
- **Mandatory cost disclosure:** the Murabaha contract cannot be generated without `cost_price`, `profit_amount`, and `total_repayable` all populated — enforced by `NOT NULL` DB constraints, not just application logic.

## Known cross-service gaps (from `docs/PRODUCTION_GAPS_REPORT.md`, 2026-04-27 — verified against code)

These are described here because they break the "immutable sequence" at exactly the points that matter most financially:

1. **`loan.created` is never published.** Gateway's contract-signing service creates a `Loan` record in the database but no service publishes the corresponding event. Ledger Service listens for it to post the initial liability/receivable journal entries — so **every loan in the system is currently missing its foundational GL entries.** This is the single highest-severity cross-service gap identified in the audit.
2. **Checkout completion is a stub.** `CheckoutFormFiller.run_checkout()` — the code that actually enters VCN payment details and detects order confirmation — is incomplete. No automated purchase can finish step 10 today.
3. **Installment auto-collection is not connected.** `BillingSweepWorker` (Ledger Service) correctly identifies overdue installments and accrues late fees, but has no call path into Payment Orchestrator to actually attempt a charge. Step 12's "auto-collected" is not automatic in the current build.
4. **Payment confirmation and order-status update are separate, uncompensated transactions.** If Payment Orchestrator marks a payment `CAPTURED` internally but its callback to Gateway fails, the order silently stays at `contracts_signed` while the money has moved — no saga/compensation logic exists.
5. **No credit reservation at order initiation.** `available_credit` is not decremented when an order starts, so two concurrent orders from the same user can each reserve the user's full limit.

None of these change the *intended* design described in this document — they are implementation gaps against that design, tracked for engineering to close. See `docs/PRODUCTION_GAPS_REPORT.md` Priority 1 checklist for the authoritative, current list.

## Expected outcome

Order reaches status `completed`: product delivered, all installments paid, loan `status = 'fully_paid'`.

## Related documents

[`05-customer-journey-e2e.md`](05-customer-journey-e2e.md), [`../03-bnpl-financing/16-financing-state-machine.md`](../03-bnpl-financing/16-financing-state-machine.md), [`../06-api-events/24-event-catalog.md`](../06-api-events/24-event-catalog.md).
