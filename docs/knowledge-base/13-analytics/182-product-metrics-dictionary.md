# Product Metrics Dictionary

**Status:** STABLE — the product-usage-funnel-specific slice of [`42-kpi-metrics-dictionary.md`](42-kpi-metrics-dictionary.md), which remains the general index; this document defines the metrics that specifically track product engagement/funnel behavior rather than financial or risk outcomes.

## Funnel metrics

| Metric | Definition |
|---|---|
| Registration → KYC start rate | % of registered users who begin KYC |
| KYC completion rate | % of KYC starts that reach `approved` (Tier 1 or manual) |
| KYC → first URL paste rate | % of KYC-approved users who submit at least one product URL |
| Extraction success rate | % of submitted URLs that produce a valid UPO (vs. `extraction_failed`) |
| Offer → contract-signing rate | % of presented offers that proceed to Wakalah signing |
| Contract signing → down payment rate | % of signed Murabaha contracts that reach down payment collection |
| **Checkout completion rate** | % of issued VCNs that result in a confirmed purchase — **currently expected to be very low**, given the checkout-automation completion gap (`PS-BL-03`); this metric, once instrumented, will be the most direct quantitative confirmation of that gap's real-world impact |
| Delivery confirmation rate | % of confirmed purchases that reach `delivered` |
| Full-loop completion rate | % of URL submissions that reach `completed` (loan fully paid) — the single metric that most directly represents "the product worked end to end" for a given attempt |

## Why this document exists separately from BNPL KPIs

[`183-bnpl-kpis.md`](183-bnpl-kpis.md) covers financing-outcome metrics (approval rate, default rate) — this document covers **product-funnel** metrics that exist regardless of the financing outcome, tracking where in the *product experience* users drop off, which is a distinct diagnostic question from "is the financing product performing well."

## Instrumentation status

None of the funnel-stage-to-stage conversion metrics above are confirmed as currently instrumented/queryable via any documented admin endpoint — `GET /admin/analytics/funnel` exists as a concept (per [`42-kpi-metrics-dictionary.md`](42-kpi-metrics-dictionary.md)) but its exact stage definitions aren't confirmed to match this table. Recommend Product/Analytics confirm and align.

## Related documents

[`42-kpi-metrics-dictionary.md`](42-kpi-metrics-dictionary.md), [`183-bnpl-kpis.md`](183-bnpl-kpis.md), [`188-executive-dashboard-specification.md`](188-executive-dashboard-specification.md).
