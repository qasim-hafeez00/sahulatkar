# BNPL KPIs

**Status:** STABLE

## Core KPIs

| KPI | Definition | Traffic-light threshold (where defined) |
|---|---|---|
| GMV | Total value of products financed | — |
| Approval rate | % of credit checks resulting in approval | Green >70%, Yellow 65–70%, Red <65% |
| Default rate | % of loans reaching `defaulted` | Green <1.5%, Yellow 1.5–2.5%, Red >2.5% |
| Collection rate | % of due installments collected on time | Green >90%, Yellow 85–90%, Red <85% |
| Average order value (AOV) | Mean purchase amount per order | — |
| Plan mix | Distribution of orders across `pay_in_3`/`pay_in_4`/`pay_in_6`/`pay_full` | — |
| Repeat purchase rate | % of customers placing a second order | — |
| Average loan tenure | Mean time from loan creation to full repayment | — |

## Relationship to the platform's specific model

Unlike a merchant-network BNPL provider, GMV here directly equals SahulatKar's own purchasing spend (since it's the actual purchaser, not just a financier sitting atop a merchant transaction) — worth noting because it changes how GMV growth should be read from a working-capital perspective (see [`../19-payments-financial-operations/104-settlement-schedule.md`](../19-payments-financial-operations/104-settlement-schedule.md)'s cash-flow note): every dollar of GMV growth is a dollar SahulatKar itself has spent before full customer repayment, not merely a transaction volume passing through the platform.

## Data-quality caveat

Given the confirmed ledger-integrity gaps (unvalidated debit=credit, missing `loan.created` events — see [`../20-ledger-accounting/113-ledger-invariants.md`](../20-ledger-accounting/113-ledger-invariants.md)), GMV and revenue-derived KPIs sourced from ledger data should currently be treated with the same caution as any other ledger-derived report — see [`../20-ledger-accounting/117-financial-reporting.md`](../20-ledger-accounting/117-financial-reporting.md).

## Related documents

[`182-product-metrics-dictionary.md`](182-product-metrics-dictionary.md), [`185-financial-kpis.md`](185-financial-kpis.md), [`42-kpi-metrics-dictionary.md`](42-kpi-metrics-dictionary.md).
