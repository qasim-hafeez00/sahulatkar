# Monitoring & Logging

**Status:** PLANNED — this entire document describes target design from `docs/MASTER_PLAN.md` §15. Per the 2026-04-27 audit, essentially none of it is operational yet (`INF-GAP-01` through `INF-GAP-04`); this is one of the largest gaps between documented intent and current reality anywhere in the platform.

## Target stack

```
Metrics:    Prometheus + Grafana (EKS addon)
Logging:    Fluent Bit → CloudWatch Logs → OpenSearch
Tracing:    OpenTelemetry → Jaeger / X-Ray
Alerting:   Grafana Alerting → Slack + PagerDuty
Uptime:     AWS Route 53 health checks
```

## Target dashboards

1. **Service Health** — request rate, error rate, latency p50/p95/p99, per service.
2. **Credit Engine** — scoring latency, approval rate, band distribution.
3. **Payment Flow** — success rate per gateway, reconciliation status.
4. **Queue Depth** — BullMQ queue sizes, consumer lag.
5. **Database** — connection pool usage, query latency, replication lag.
6. **Business KPIs** — GMV, active users, default rate, revenue. Cross-reference: [`../13-analytics/42-kpi-metrics-dictionary.md`](../13-analytics/42-kpi-metrics-dictionary.md).

## Target alerting rules (PagerDuty)

| Condition | Severity |
|---|---|
| Error rate >5% for 5 min | P1 |
| Credit Engine p99 >3s | P2 |
| Payment webhook failures >3 in 10 min | P1 |
| Database connection pool >80% | P2 |
| Redis memory >90% | P2 |
| Pod restart count >3 in 15 min | P2 |

## What's actually running today

Each service exposes a `/metrics` Prometheus endpoint and `/health`/`/health/ready` liveness/readiness probes checking DB/Redis/listener health — this scaffolding is in place. **Everything downstream of "the metrics exist" is not yet built:** no Grafana dashboards are defined, no alerting rules are configured, no log shipper is running (logs are lost on pod restart), no tracing collector exists, and `X-Request-ID` — generated at the Gateway specifically to enable cross-service tracing — is not actually forwarded to any downstream service, so even manual log correlation across the 12-step flow isn't possible today without extra work per incident.

**Practical implication:** until this is built, the platform currently has no way to detect an incident other than a human noticing (a customer complaint, a manual check) or reading pod logs directly — see [`../12-operations/41-incident-response-plan.md`](../12-operations/41-incident-response-plan.md) for how this should shape near-term on-call practice.

## DLQ monitoring (specific, recurring gap)

At least 4 separate dead-letter-queue systems exist across services (scraping, checkout, notification, ledger events) with no unified monitoring — items can accumulate indefinitely with nobody alerted (`INF-GAP-05`). This is a direct consequence of the missing alerting layer above and should be one of the first alerts configured once Grafana Alerting is stood up.

## Related documents

[`33-infrastructure-architecture.md`](33-infrastructure-architecture.md), [`../12-operations/41-incident-response-plan.md`](../12-operations/41-incident-response-plan.md), [`../13-analytics/42-kpi-metrics-dictionary.md`](../13-analytics/42-kpi-metrics-dictionary.md).
