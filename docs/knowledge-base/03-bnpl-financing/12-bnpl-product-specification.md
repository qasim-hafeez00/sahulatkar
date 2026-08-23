# BNPL Product Specification

**Status:** STABLE

## What the product is

SahulatKar's financing product is a single-item, agency-Murabaha-structured BNPL: a customer selects one product (via pasted URL), SahulatKar purchases it on their behalf under a Wakalah agency agreement, then sells it to them at cost plus a disclosed profit under a Murabaha contract, repaid over a fixed installment schedule. There is no revolving credit line, no multi-item basket financing, and no cash-out product — one order maps to one loan.

## Structure

```
Order (1 product, 1 URL)
  → Wakalah Agreement (agency to purchase)
  → Murabaha Contract (cost-plus sale + fixed installment schedule)
  → Loan (1:1 with order)
  → Installments (down payment + N scheduled payments)
```

## Purchase amount

Cost price (as extracted/quoted by the product source) plus shipping, in PKR. Subject to a ±5% price-variance tolerance between the Wakalah authorization and actual purchase execution (see `authorized_amount` / `price_variance_pct` on `wakalah_agreements`).

## Down payment

25–40% of the financed amount, collected before VCN issuance. Percentage is determined by the customer's credit band, not a fixed platform-wide number. Full rules: [`15-credit-limit-rules.md`](15-credit-limit-rules.md).

## Financed amount

`purchase amount − down payment`, split into equal installments per the selected plan (last installment rounding-adjusted).

## Installment amount & tenure

Governed by plan selection — see [`13-payment-plan-rules.md`](13-payment-plan-rules.md).

## Fees

The only fee in the product is the disclosed Murabaha profit margin, baked into `total_repayable` at contract signing — no separate service fee, no compounding, no hidden charges. Late fees exist as a mechanism but are 100% charity-routed (not retained platform revenue). Full economics: [`../01-company-product/03-business-model.md`](../01-company-product/03-business-model.md).

## Settlement

SahulatKar settles with the payment gateways it collects through (Safepay/JazzCash/EasyPaisa), not with merchants — see [`../02-business-workflows/11-merchant-settlement-reconciliation.md`](../02-business-workflows/11-merchant-settlement-reconciliation.md).

## Immutability after signing

Once the Murabaha contract is signed, the installment schedule, cost price, and profit amount are fixed and cannot be altered — this is a Shariah requirement (the sale price of a Murabaha transaction must be fixed at contract time), not just a UX choice. Any post-signing change (e.g., a payment restructuring) must be modeled as a new agreement/addendum, not a mutation of the original contract record. (Payment restructuring itself — `POST /admin/orders/{order_id}/restructure` — is speced as an admin capability (AD-08) but not yet implemented, per `GW-GAP-05`.)

## Related documents

[`13-payment-plan-rules.md`](13-payment-plan-rules.md), [`14-eligibility-rules.md`](14-eligibility-rules.md), [`15-credit-limit-rules.md`](15-credit-limit-rules.md), [`16-financing-state-machine.md`](16-financing-state-machine.md), [`../04-shariah/17-shariah-product-structure.md`](../04-shariah/17-shariah-product-structure.md).
