# Operations KPIs

**Status:** STABLE

## KPIs

| KPI | Definition | Target/threshold |
|---|---|---|
| HITL SLA compliance | % of HITL escalations resolved within 15 minutes | Not formally defined — recommend a target (e.g., ≥90%) |
| KYC manual-review SLA compliance | % of manual KYC reviews decided within 24 hours | Not formally defined |
| Checkout automation success rate | % of checkout attempts completing without HITL escalation | Currently expected very low given `PS-BL-03` — see [`182-product-metrics-dictionary.md`](182-product-metrics-dictionary.md) |
| DLQ backlog size (per queue) | Items stuck in each of the 4 fragmented DLQ systems | Should be near-zero; not currently monitored (`INF-GAP-05`) |
| Support ticket volume/resolution time | Once general support ticketing exists (AD-14/AD-15) | Not applicable today — no ticketing system built |
| Delivery exception rate | % of shipments hitting `attempted`, `returned`, or `lost` status | — |

## Why several rows above have no defined target

This mirrors a pattern across the whole knowledge base: mechanisms with well-specified SLAs (HITL 15 min, KYC 24hr) don't yet have a correspondingly tracked *compliance rate* against those SLAs — the SLA exists as a policy, but nothing currently measures whether it's actually being met. Recommend Ops/Analytics close this specific gap first, since it's cheap (the underlying timestamp data already exists in `hitl_queue`/`kyc_verification_queue`) and would immediately surface whether the documented SLAs reflect reality.

## Related documents

[`../12-operations/39-customer-support-sop.md`](../12-operations/39-customer-support-sop.md), [`../06-api-events/128-retry-dead-letter-strategy.md`](../06-api-events/128-retry-dead-letter-strategy.md), [`42-kpi-metrics-dictionary.md`](42-kpi-metrics-dictionary.md).
