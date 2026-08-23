# KPI / Metrics Dictionary

**Status:** STABLE — sourced from `docs/System-md-files/M10-M12-delivery-ledger-admin.md` (M12 admin dashboard spec).

## Executive dashboard KPIs

| Metric | Definition | Source |
|---|---|---|
| GMV | Gross merchandise value — total value of products financed | `mv_daily_revenue` |
| Active users | Users with `status='active'` and recent activity (exact recency window not specified — confirm with Product) | `users` |
| Approval rate | % of credit checks resulting in approval | Credit Engine / `risk_assessments` |
| Default rate | % of loans reaching `defaulted` status | `loans` |
| Revenue (month) | Sum of Murabaha profit + affiliate commission recognized in period | `journal_entries` (revenue accounts 4001–4003) |
| Orders today | Count of orders created today | `orders` |
| Payments due | Sum of `installments` due today | `installments` |
| Overdue amount | Sum of `installments.total_amount` where `status='overdue'` | `installments` |
| Collection rate | % of due installments collected on time | `installments` |
| Fraud loss rate | Fraud-attributed losses / GMV | Credit Engine + Ledger |
| NPS | Net Promoter Score | Not sourced from a specific table in current docs — presumably a survey-based external metric |

## Traffic-light thresholds (already defined for the admin dashboard)

| Metric | Green | Yellow | Red |
|---|---|---|---|
| Default rate | <1.5% | 1.5–2.5% | >2.5% |
| Collection rate | >90% | 85–90% | <85% |
| Approval rate | >70% | 65–70% | <65% |
| Fraud loss rate | <0.2% | 0.2–0.3% | >0.3% |

## Cohort metrics

`GET /admin/analytics/cohort?type=retention|ltv&months=12` — grid of cohort rows × months, values = % repeat purchase (retention) or cumulative PKR/user (LTV). **Known gap:** this endpoint is speced but not implemented (`GW-GAP-12`).

## Funnel metrics

`GET /admin/analytics/funnel` — acquisition funnel + order-completion funnel with conversion rate and drop-off at each stage. Given the current checkout-completion gap (`PS-BL-03`), the "purchase execution" stage of this funnel should be watched especially closely once instrumented, since it's expected to show a severe drop-off until that gap closes.

## Executive metrics with target-vs-actual tracking (speced)

GMV growth, Revenue growth, CAC, LTV:CAC, Approval rate, Collection rate, Default rate, NPS — via `GET /admin/analytics/dashboard`. No numeric targets for these are documented in current engineering docs beyond the traffic-light thresholds above — **Product/Finance should set explicit targets**, since "target vs actual" tracking requires a target to exist.

## Materialized views feeding these metrics

`mv_daily_revenue` (GMV, gross profit, AOV per day), `mv_loan_portfolio` (status counts, outstanding totals, defaults), `mv_merchant_performance` (orders, GMV, checkout success rate per tracked merchant) — refreshed nightly. See [`../07-database/25-database-architecture.md`](../07-database/25-database-architecture.md).

## Recommended additions (not currently tracked, identified as gaps elsewhere in this knowledge base)

- **Merchant-ban rate** — how often a third-party site's own fraud detection blocks the checkout agent's purchasing pattern (see [`../12-operations/40-merchant-vendor-support-sop.md`](../12-operations/40-merchant-vendor-support-sop.md)).
- **Checkout automation success rate** — the platform-wide % of purchase attempts the agent completes without HITL escalation; central to the product's core value proposition and currently near the bottom given `PS-BL-03`, but not called out as a named executive KPI in current docs the way default rate and approval rate are.
- **HITL SLA compliance rate** — % of HITL escalations resolved within the 15-minute SLA.
- **DLQ backlog size**, per queue — an operational health metric, relevant given the unified-DLQ-monitoring gap noted in [`../10-devops/35-monitoring-logging.md`](../10-devops/35-monitoring-logging.md).

## Related documents

[`../10-devops/35-monitoring-logging.md`](../10-devops/35-monitoring-logging.md) (dashboard #6, Business KPIs), [`../05-architecture/microservices/gateway.md`](../05-architecture/microservices/gateway.md) (admin analytics endpoints).
