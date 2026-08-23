# Executive Dashboard Specification

**Status:** STABLE (spec) — expanded from [`42-kpi-metrics-dictionary.md`](42-kpi-metrics-dictionary.md), consolidating the executive-level view specifically.

## Spec

`GET /admin/analytics/dashboard` — executive metrics with target-vs-actual tracking: GMV growth, Revenue growth, CAC, LTV:CAC, Approval rate, Collection rate, Default rate, NPS. Refresh cadence for the general admin dashboard is documented as every 60 seconds, sourced from a read replica (per `docs/System-md-files/M10-M12-delivery-ledger-admin.md`).

## Recommended layout (proposed, not specified in engineering docs beyond the metric list)

```
Row 1 — Health at a glance: GMV (this month, trend), Default rate (traffic light),
        Approval rate (traffic light), Collection rate (traffic light)
Row 2 — Growth: GMV growth %, Revenue growth %, CAC, LTV:CAC
Row 3 — Risk: Credit band distribution, Fraud loss rate, Portfolio concentration
        (flag any category/city/merchant approaching its Layer 7 cap)
Row 4 — Operations: HITL SLA compliance, Checkout automation success rate,
        DLQ backlog (once tracked)
Row 5 — Customer: NPS, repeat purchase rate, complaint volume (once tracked)
```

## No numeric targets currently set

Per [`42-kpi-metrics-dictionary.md`](42-kpi-metrics-dictionary.md), "target vs. actual" tracking is speced but no actual target values are documented anywhere — Product/Finance/Risk leadership need to set these before the dashboard's target-vs-actual framing is meaningful rather than just showing "actual" against a blank target.

## Data-integrity caveat, restated once more because it applies here too

Any dashboard number sourced from ledger data (GMV, revenue, margin) inherits the caveat in [`186-financial-kpis.md`](186-financial-kpis.md) — an executive dashboard is exactly the place where a subtly wrong number does the most damage (a bad decision made confidently on bad data), so this caveat is worth surfacing directly on the dashboard itself (e.g., a visible "data integrity: verified / unverified" indicator) rather than only in this document, until the underlying ledger gaps are closed.

## Related documents

[`42-kpi-metrics-dictionary.md`](42-kpi-metrics-dictionary.md), [`186-financial-kpis.md`](186-financial-kpis.md), [`../20-ledger-accounting/117-financial-reporting.md`](../20-ledger-accounting/117-financial-reporting.md).
