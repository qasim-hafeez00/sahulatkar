# Refund & Cancellation Workflow

**Status:** PLANNED / INTERNAL DRAFT — this is the area with the least implemented functionality and the least documented policy in the entire platform. Treat this document as a starting design brief for Product + Legal + Engineering to complete, not a description of a working feature.

## What exists today

- **Cancellation:** `POST /api/v1/orders/{order_id}/cancel` is implemented for orders in `url_received`, `offer_presented`, `offer_accepted`, or `extraction_failed`. Credit is meant to be restored on cancel (`available_credit += loan.principal`) but since credit is never actually reserved at order initiation (see [`07-bnpl-workflow-e2e.md`](07-bnpl-workflow-e2e.md) known gaps), this increment currently adds credit that was never subtracted — a real accounting bug, not just a missing feature.
- **Refund:** `RefundOrchestrator.initiate_refund()` in Payment Orchestrator is a stub with no implementation. The customer-facing endpoint (`POST /api/v1/payments/refund/{order_id}`) does not exist yet either (`GW-GAP-11`). **There is currently no way to refund a customer through the system.**

## Gap: no exit path between contract signing and VCN issuance

Cancellation is not currently allowed once an order reaches `contracts_signed` but before a VCN has been issued or money spent on the actual purchase — even though no irreversible action has happened yet at that point. Both the customer and admin currently have no way to unwind an order stuck in this window (`GW-BL-04`). This should be one of the first gaps closed, since it's a pure state-machine fix (no money has moved) rather than a financial-reconciliation problem.

## Target design (for Product/Legal/Engineering to complete)

The following is a reasonable target shape based on the state machine and existing patterns elsewhere in the platform — **not yet approved policy**:

### Cancellation, by order state

| Order state | Cancellable? | What should happen |
|---|---|---|
| `url_submitted` … `offer_presented` | Yes (implemented) | Order closed, no financial impact |
| `contracts_signed`, pre-VCN | **Should be, currently isn't** | Order closed, contracts voided, no financial impact (no down payment collected until after this point per "collect first, then buy" — confirm this ordering before finalizing policy, since down payment actually precedes VCN issuance in the 12-step flow, meaning down payment IS collected by this state) |
| Post-down-payment, pre-VCN | Needs design | Requires an actual refund of the down payment — blocked on `RefundOrchestrator` being built |
| Post-VCN, pre-checkout | Needs design | Requires VCN void + down payment refund |
| Post-checkout (product purchased) | Needs design | This is a **merchant return**, not a platform cancellation — subject to the merchant-return risk described in [`06-merchant-vendor-journey.md`](06-merchant-vendor-journey.md). Needs an explicit policy on who absorbs the cost when a merchant refuses a third-party return. |
| Post-delivery | Needs design | Standard consumer return/refund process, still gated on merchant acceptance |

### Refund triggers to design for

- Customer-initiated cancellation (see table above)
- Out-of-stock / price-changed-beyond-tolerance at checkout time (agent cannot complete purchase)
- Merchant checkout failure (site down, blocked, HITL exhausted)
- Product not delivered / lost in transit
- Product returned by customer, merchant accepts return
- Product returned by customer, merchant refuses return — **who absorbs the loss is an open policy question**

### What a complete refund flow needs (none of this exists yet)

1. `RefundOrchestrator.initiate_refund()` implementation — routes to the correct gateway (Safepay/JazzCash/EasyPaisa) for the original payment method.
2. VCN void on cancellation, wired to the `order.cancelled` event (currently no handler exists in Payment Orchestrator for this event at all).
3. Ledger entries for the refund (currently no `refund` entry type is exercised in code, though `entry_type` on `journal_entries` includes `'refund'` in its schema).
4. Customer-facing refund status visibility (schedule, expected timing).
5. Customer notification on cancellation (`GW-BL-10` — currently no notification is sent).

## Related documents

[`05-customer-journey-e2e.md`](05-customer-journey-e2e.md), [`../03-bnpl-financing/16-financing-state-machine.md`](../03-bnpl-financing/16-financing-state-machine.md), [`06-merchant-vendor-journey.md`](06-merchant-vendor-journey.md), `docs/PRODUCTION_GAPS_REPORT.md` §4 (Payment Orchestrator Gaps, PO-CRIT-01).
