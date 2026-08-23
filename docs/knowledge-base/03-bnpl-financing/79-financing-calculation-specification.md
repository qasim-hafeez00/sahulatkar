# Financing Calculation Specification

**Status:** STABLE — the exact-arithmetic specification underlying [`77-financing-model.md`](77-financing-model.md), written for anyone implementing or auditing the calculation code itself.

## Source code reference

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

(From `docs/System-md-files/M03-url-pipeline.md`, Product Service's `pricing_service.py`.)

## Precision requirements

Every intermediate and final value must be `DECIMAL(14,2)` (PKR to the paisa), never a float — this is a platform-wide immutable rule (see [`../07-database/25-database-architecture.md`](../07-database/25-database-architecture.md)). The `round()` call on `markup` in the snippet above should be understood as rounding to the nearest paisa (2 decimal places), not to a whole rupee — any implementation or audit should verify this explicitly against the actual code, since the pseudocode above doesn't show the rounding precision argument.

## Installment splitting

`total_repayable ÷ installment_count`, with the **last installment absorbing the rounding remainder** so the sum of all installments exactly equals `total_repayable` to the paisa — no installment should be silently off by a fraction of a paisa due to naive division. This is stated as a design rule ("last one rounding-adjusted") but the exact rounding algorithm (does installment 1 through N−1 round down and N absorb the surplus, or round-half-up per installment with N absorbing the residual?) is not specified at the level of exact arithmetic in current engineering docs — recommend this be pinned down in code comments/tests if not already, since it's exactly the kind of ambiguity that produces the "off by a paisa across thousands of loans" class of bug.

## Down payment calculation

`down_payment = purchase_amount × down_payment_pct`, where `down_payment_pct` comes from the credit band (25/30/33/40% depending on band — see [`15-credit-limit-rules.md`](15-credit-limit-rules.md)), **not** from the plan type. Down payment is subtracted before the plan markup is applied — i.e., the markup is calculated on the *financed* amount, not the full purchase price. Confirm this ordering against actual code before relying on it for financial modeling, since a markup calculated on the full price instead of the financed amount would produce materially different (higher) profit figures.

## Testing implications

Every financial calculation described here should have an exact-decimal test asserting the installment sum equals `total_repayable` precisely — see [`../09-qa/32-financial-transaction-test-strategy.md`](../09-qa/32-financial-transaction-test-strategy.md) for the broader exact-decimal testing discipline this specification feeds into.

## Related documents

[`77-financing-model.md`](77-financing-model.md), [`13-payment-plan-rules.md`](13-payment-plan-rules.md), [`../09-qa/32-financial-transaction-test-strategy.md`](../09-qa/32-financial-transaction-test-strategy.md).
