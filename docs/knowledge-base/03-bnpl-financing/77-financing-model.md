# Financing Model

**Status:** STABLE — the numeric/structural model underlying [`12-bnpl-product-specification.md`](12-bnpl-product-specification.md), pulled out as its own document for readers who specifically need the calculation model rather than the product description.

## Model structure

```
Purchase amount = product cost + shipping
Down payment     = Purchase amount × down_payment_pct (25–40%, band-determined)
Financed amount  = Purchase amount − Down payment
Profit (markup)  = Financed base × plan markup rate (2.5% / 4.0% / 7.0%, tiered by plan)
Total repayable  = Financed amount + Profit
Installment amt  = Total repayable ÷ installment count (last one rounding-adjusted)
```

## Worked example

PKR 20,000 product, Band B customer (25% down, `pay_in_4` selected):

```
Down payment    = 20,000 × 0.25 = 5,000
Financed amount = 15,000
Profit (4.0%)   = 15,000 × 0.04 = 600
Total repayable = 15,600
Per installment = 15,600 ÷ 4 = 3,900
```

Customer pays PKR 5,000 today, then 4 installments of PKR 3,900 biweekly = PKR 20,600 total (PKR 600 more than the item's cash price, fully disclosed before signing).

## Where each input comes from

- Product cost & shipping: Product Service's UPO (`pricing` block).
- Down payment %: Credit Engine's band assignment (see [`15-credit-limit-rules.md`](15-credit-limit-rules.md)).
- Markup rate: hardcoded per plan (see [`13-payment-plan-rules.md`](13-payment-plan-rules.md); **not yet Shariah-board approved**).
- Installment count: customer's plan selection, constrained to what their approval allows.

## Relationship to the ledger

Each component above maps to a specific chart-of-accounts entry once the loan is created: financed amount → Financing Receivable (asset), profit → Murabaha Profit (revenue), recognized incrementally or at signing depending on the accounting policy chosen (not explicitly specified in current engineering docs — Finance should confirm revenue-recognition timing). See [`../20-ledger-accounting/`](../20-ledger-accounting/).

## Related documents

[`12-bnpl-product-specification.md`](12-bnpl-product-specification.md), [`13-payment-plan-rules.md`](13-payment-plan-rules.md), [`79-financing-calculation-specification.md`](79-financing-calculation-specification.md).
