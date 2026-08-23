# Credit / Risk KPIs

**Status:** STABLE

## KPIs

| KPI | Definition | Threshold (where defined) |
|---|---|---|
| Approval rate | See [`183-bnpl-kpis.md`](183-bnpl-kpis.md) | Green >70%, Yellow 65–70%, Red <65% |
| Default rate | See [`183-bnpl-kpis.md`](183-bnpl-kpis.md) | Green <1.5%, Yellow 1.5–2.5%, Red >2.5% |
| Fraud loss rate | Fraud-attributed losses ÷ GMV | Green <0.2%, Yellow 0.2–0.3%, Red >0.3% |
| Credit band distribution | % of applicants in each band (A–F) | — |
| Manual review rate | % of applications routed to manual review rather than auto-decided | — (recommend a target be set — a very high manual-review rate suggests the automated model's confidence thresholds may need tuning) |
| Portfolio concentration (by category/city/merchant) | Actual % vs. the Layer 7 caps | Red if approaching or exceeding the defined cap (25%/40%/20%/etc. — see [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md)) |
| Override rate | % of automated decisions manually overridden | Not currently tracked — recommended addition, see [`../18-credit-risk-policy/96-risk-override-policy.md`](../18-credit-risk-policy/96-risk-override-policy.md) |
| Blacklist hit rate | % of applications hitting a Layer 1 blacklist block | — |

## Why override rate deserves explicit tracking

An override that bypasses the automated model is only safe if overridden decisions don't systematically underperform automated ones — without tracking this, Risk has no way to know whether the override mechanism is being used judiciously or is quietly eroding the credit book's quality. Flagged here as a recommended addition, cross-referenced from [`../18-credit-risk-policy/96-risk-override-policy.md`](../18-credit-risk-policy/96-risk-override-policy.md).

## Related documents

[`../18-credit-risk-policy/87-credit-risk-framework.md`](../18-credit-risk-policy/87-credit-risk-framework.md), [`../18-credit-risk-policy/92-risk-segmentation.md`](../18-credit-risk-policy/92-risk-segmentation.md), [`42-kpi-metrics-dictionary.md`](42-kpi-metrics-dictionary.md).
