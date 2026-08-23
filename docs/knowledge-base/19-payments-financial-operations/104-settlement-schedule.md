# Settlement Schedule

**Status:** STABLE

## By gateway (customer collections → SahulatKar's bank account)

| Gateway | Settlement timing |
|---|---|
| Safepay | T+2 |
| JazzCash | T+1 |
| EasyPaisa | T+1 |
| Raast | T+0 (not yet live) |

## By merchant (SahulatKar's payment → third-party site)

**Immediate, at time of checkout** — via the VCN, same as any card-present-equivalent retail transaction. There is no deferred merchant settlement schedule because there is no deferred merchant payment; see [`../17-merchant-documentation/72-merchant-settlement-flow.md`](../17-merchant-documentation/72-merchant-settlement-flow.md).

## Cash-flow implication worth surfacing to Finance explicitly

SahulatKar pays the merchant **immediately** at checkout (full product cost, out of pocket) but only collects the down payment **before** that point and the remaining installments **over the following weeks** — meaning SahulatKar is genuinely financing the purchase from its own capital between checkout and full customer repayment, which is the core working-capital dynamic of the business (this is true of any BNPL provider, but worth stating explicitly here since the settlement-timing tables above are exactly the inputs a working-capital/cash-flow model would need). No documented working-capital or cash-flow-timing model exists elsewhere in engineering docs — this would be a natural addition to [`../01-company-product/03-business-model.md`](../01-company-product/03-business-model.md) for Finance to build out.

## Related documents

[`102-payment-reconciliation.md`](102-payment-reconciliation.md), [`../01-company-product/03-business-model.md`](../01-company-product/03-business-model.md), [`../17-merchant-documentation/72-merchant-settlement-flow.md`](../17-merchant-documentation/72-merchant-settlement-flow.md).
