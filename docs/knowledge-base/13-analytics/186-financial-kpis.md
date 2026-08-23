# Financial KPIs

**Status:** STABLE (definitions) — sourced heavily from data whose integrity is currently uncertain; caveat repeated deliberately.

## KPIs

| KPI | Definition |
|---|---|
| Revenue (Murabaha profit + affiliate commission) | See [`../01-company-product/03-business-model.md`](../01-company-product/03-business-model.md) |
| Net contribution margin | Revenue minus gateway fees, extraction costs, VCN issuance, SMS/infra — per-order, then aggregated |
| Break-even default rate | The default rate above which a cohort's contribution margin goes negative — reference figure ~1.9% on a PKR 10,000 order (see [`../01-company-product/03-business-model.md`](../01-company-product/03-business-model.md)) |
| Working capital deployed | Cumulative merchant spend not yet recovered via customer repayment — see [`../19-payments-financial-operations/104-settlement-schedule.md`](../19-payments-financial-operations/104-settlement-schedule.md) |
| Charity disbursed (late fees) | Should equal charity accrued — a compliance-relevant financial KPI, not just an accounting one |
| Gateway fee ratio | Total gateway fees ÷ GMV — tracks payment-processing cost efficiency across the 3 gateways |

## The caveat that applies to every KPI in this table

Per [`../20-ledger-accounting/117-financial-reporting.md`](../20-ledger-accounting/117-financial-reporting.md), the ledger's own invariants (debit=credit, `loan.created` event delivery) are not currently enforced/functioning — meaning any of the KPIs above, if sourced from ledger data, should be treated as **directionally illustrative, not precise**, until those gaps close. Finance should confirm the actual data source for each KPI above (ledger-derived vs. computed directly from `payment_transactions`/`loans` records) and flag which are currently trustworthy vs. which inherit the ledger-integrity caveat.

## Related documents

[`../01-company-product/03-business-model.md`](../01-company-product/03-business-model.md), [`../20-ledger-accounting/117-financial-reporting.md`](../20-ledger-accounting/117-financial-reporting.md), [`183-bnpl-kpis.md`](183-bnpl-kpis.md).
