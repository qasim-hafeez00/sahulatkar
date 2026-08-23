# Payment Plan Rules

**Status:** STABLE (mechanics) · markup rates flagged as pending Shariah board approval.

## Available plans

| Plan | Installments | Markup rate | Status |
|---|---|---|---|
| `pay_in_3` | 3 | 2.5% | Coded, **not yet Shariah-board-approved** (`pricing_service.py:22` TODO) |
| `pay_in_4` | 4 | 4.0% | Coded, same open item |
| `pay_in_6` | 6 | 7.0% | Coded, same open item |
| `pay_full` | 1 (pay in full) | N/A | Referenced in `loans.plan_type` CHECK constraint |

Elsewhere in engineering docs, "4% flat" is used as a simplified reference figure for the platform's markup in general (e.g. the quick-reference table). This document reflects what's actually coded: a **tiered** structure by plan length, not a flat rate. Product/Compliance should reconcile which figure is the intended final design before external communication.

## Pricing calculation

```python
MARKUP_RATES = {
  'pay_in_3': 0.025,
  'pay_in_4': 0.040,
  'pay_in_6': 0.070,
}

def calculate_schedule(product_cost_pkr, shipping_pkr, plan_type):
    cost = product_cost_pkr + shipping_pkr
    markup = round(cost * MARKUP_RATES[plan_type])
    total = cost + markup
    # Equal installments; last one rounding-adjusted
```

Mandatory disclosure: `cost_price`, `profit_amount`, and `total` (→ `total_repayable`) must all be computed and shown before a contract can be generated — this is enforced at the database level on `murabaha_contracts` (`NOT NULL` on all three), not just in the pricing service.

## Minimum / maximum purchase

Not specified as an explicit platform-wide minimum/maximum in current engineering docs beyond what a user's credit band and cold-start cap allow (see [`15-credit-limit-rules.md`](15-credit-limit-rules.md)) — i.e., the *de facto* range is governed entirely by credit limits, not a separate order-size policy. Recommend Product confirm whether a standalone min/max order value policy is needed (e.g., a floor below which financing isn't offered at all) since none is currently documented.

## Allowed frequencies

Biweekly, per the installment collection design (see [`../02-business-workflows/08-payment-workflow.md`](../02-business-workflows/08-payment-workflow.md)). No monthly or weekly cadence is documented as an option.

## Down-payment validation gap

**Known gap (PS-BL-11, PO-BL-04):** the 25–40% down-payment range is currently hardcoded rather than read from the `system_parameters` table, and Payment Orchestrator does not validate the client-submitted `down_payment_pct` against any server-side bound beyond a 1 PKR tolerance check — meaning admin cannot adjust this range without a code deploy, and there is no defense against a malformed/malicious down-payment percentage from the client today. This should be closed before launch.

## Eligibility conditions for plan selection

Not separately gated per plan in current engineering docs beyond overall order-amount eligibility (see [`14-eligibility-rules.md`](14-eligibility-rules.md)) — i.e., a customer approved for an order at all currently sees all three plans as options, with the higher-installment-count plans naturally carrying a higher total cost due to the tiered markup. Whether risk band should restrict which plans are offered (e.g., Band D customers limited to `pay_in_3` only) is not specified — a Risk/Product decision to make explicitly if desired.

## Related documents

[`12-bnpl-product-specification.md`](12-bnpl-product-specification.md), [`../04-shariah/17-shariah-product-structure.md`](../04-shariah/17-shariah-product-structure.md) (markup-approval status), [`../01-company-product/03-business-model.md`](../01-company-product/03-business-model.md).
