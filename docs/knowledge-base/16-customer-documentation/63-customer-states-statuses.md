# Customer States & Statuses

**Status:** STABLE — consolidated reference of every status enum that describes "where a customer/their orders/their loans currently stand," pulled from across the module specs into one lookup table.

## Account status (`users.status`)

`pending_kyc` → `active` → `suspended` | `closed` | `blocked`

## KYC status (`user_kyc_verifications.status`)

`pending` → `processing` → `ai_approved` | `manual_review` → `approved` | `rejected`

## Order status (19-state machine)

`url_submitted` → `extracting` → `extraction_failed` | `offer_presented` → `contracts_pending` → `contracts_signed` → `down_payment_pending` → `down_payment_received` → `vcn_issued` → `purchasing` → `purchase_failed` | `purchase_confirmed` → `delivery_pending` → `in_transit` → `delivered` → `completed` | `cancelled` | `refunded` | `disputed`

Full detail: [`../03-bnpl-financing/16-financing-state-machine.md`](../03-bnpl-financing/16-financing-state-machine.md).

## Loan status (`loans.status`)

`active` → `partially_paid` → `fully_paid` | `defaulted` | `written_off` | `disputed`

## Installment status (`installments.status`)

`pending` → `paid` | `overdue` → `defaulted` | `waived` | `rescheduled`

## Contract signing status (Wakalah / Murabaha)

Wakalah: `generated` → `otp_sent` → `signed` → `executed`
Murabaha: `generated` → `otp_sent` → `signed` → `active` → `completed` | `cancelled` | `disputed`

## Why this consolidated table exists

A customer's "true current status" from a support or analytics perspective is really a composite of all six of the above — e.g., a customer can simultaneously be `active` at the account level, have an order at `delivery_pending`, and have a loan at `partially_paid`. No single field captures "the customer's overall situation," which is exactly why [`../16-customer-documentation/64-customer-experience-specification.md`](64-customer-experience-specification.md) needs to specify, screen by screen, which combination of these statuses drives what the customer actually sees.

## Related documents

[`62-customer-lifecycle.md`](62-customer-lifecycle.md), [`64-customer-experience-specification.md`](64-customer-experience-specification.md), [`../03-bnpl-financing/16-financing-state-machine.md`](../03-bnpl-financing/16-financing-state-machine.md).
