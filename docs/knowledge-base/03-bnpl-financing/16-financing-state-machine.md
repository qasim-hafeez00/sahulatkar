# Financing State Machine

**Status:** STABLE — order states sourced verbatim from `docs/System-md-files/00Sahulatkar-System.md`; loan/installment/contract states cross-referenced from `M06-M09` and `M05-contracts.md`.

## Order state machine (19 states, immutable sequence)

```
url_submitted
  → extracting
    → extraction_failed
  → offer_presented
    → contracts_pending
      → contracts_signed        ← HARD GATE: only state that permits VCN issuance
        → down_payment_pending
          → down_payment_received
            → vcn_issued
              → purchasing
                → purchase_failed
                → purchase_confirmed
                  → delivery_pending
                    → in_transit
                      → delivered
                        → completed
      | cancelled | refunded | disputed   ← terminal states, reachable from multiple points
```

**Known gap:** the transition into `cancelled` is only currently implemented from the early states (`url_received`, `offer_presented`, `offer_accepted`, `extraction_failed`) — not from `contracts_signed` onward, which is a real gap against the intended design (see [`../02-business-workflows/09-refund-cancellation-workflow.md`](../02-business-workflows/09-refund-cancellation-workflow.md)).

## Loan state machine

```
active → partially_paid → fully_paid
       → defaulted
       → written_off
       → disputed
```

Created 1:1 with a signed Murabaha contract. **Known gap:** no service currently publishes the `loan.created` event that should trigger the Ledger Service's initial journal entries — see [`../02-business-workflows/07-bnpl-workflow-e2e.md`](../02-business-workflows/07-bnpl-workflow-e2e.md).

## Installment state machine

```
pending → paid
        → overdue → defaulted
        → waived
        → rescheduled
```

Each installment additionally tracks `days_overdue`, `retry_count`, `next_retry_at`, and `late_fee_amount` (100% charity-routed on payment, see [`../02-business-workflows/10-default-collections-workflow.md`](../02-business-workflows/10-default-collections-workflow.md)).

## Contract signing states

```
WAKALAH:   generated → otp_sent → signed → executed (once the agent completes the purchase)

MURABAHA:  generated (only after Wakalah signed) → otp_sent → signed (HARD GATE UNLOCKED)
           → active (once down payment received) → completed (all installments paid)
           → cancelled (pre-delivery) | disputed
```

**Known gap:** code does not currently enforce that a Murabaha can only be *generated* after the corresponding Wakalah reaches `signed` — only that a Murabaha record exists at all (`GW-BL-03`).

## KYC state machine

```
NOT_STARTED
  → IN_PROGRESS → UPLOADING_CNIC → NADRA_CHECKING → LIVENESS_CHECKING
    → AI_APPROVED (auto-approve, triggers credit scoring)
    → PENDING_MANUAL_REVIEW (borderline) → APPROVED | REJECTED (by KYC Ops)
    → REJECTED (hard fail: emulator, blocked CNIC, <70% face match)
APPROVED → credit scoring triggered → users.status = 'active'
REJECTED → user notified with reason, may re-apply after 30 days
```

Full detail: [`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md).

## Purchase execution states (checkout agent)

```
queued → running → succeeded | failed | hitl_escalated | cancelled
```

`failed` carries a `failure_type` (`captcha`, `site_down`, `price_changed`, `out_of_stock`, `cart_error`, `payment_declined`, `checkout_changed`, `bot_detected`, `timeout`, `unknown`). Full detail: [`../05-architecture/microservices/product-service.md`](../05-architecture/microservices/product-service.md).

## VCN states

```
active → used | voided | expired | failed
```

Single-use by design — transitions to `used` after first successful charge, auto-expires 24 hours after issuance if unused. **Known gap:** local `expired` status marking does not currently trigger an actual void call to the card issuer (Stripe), leaving the card live on the issuer side for up to 24 extra hours (`PO-CRIT-04`).

## Related documents

[`../02-business-workflows/07-bnpl-workflow-e2e.md`](../02-business-workflows/07-bnpl-workflow-e2e.md), [`12-bnpl-product-specification.md`](12-bnpl-product-specification.md), [`../04-shariah/17-shariah-product-structure.md`](../04-shariah/17-shariah-product-structure.md).
