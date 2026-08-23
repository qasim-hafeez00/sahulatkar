# Alerting

**Status:** PLANNED — expanded from [`35-monitoring-logging.md`](35-monitoring-logging.md)'s alerting section, given its own document since it's the single most operationally urgent piece of the missing observability stack.

## Target alerting rules (design)

| Condition | Severity |
|---|---|
| Error rate >5% for 5 min | P1 |
| Credit Engine p99 >3s | P2 |
| Payment webhook failures >3 in 10 min | P1 |
| Database connection pool >80% | P2 |
| Redis memory >90% | P2 |
| Pod restart count >3 in 15 min | P2 |

## Current state: zero alerting exists

No Grafana Alerting, no PagerDuty integration, nothing configured — this platform currently has **no automated way to detect an incident**, relying entirely on manual observation. This is the single largest gap in [`35-monitoring-logging.md`](35-monitoring-logging.md), given its own document specifically to argue for its priority: **alerting should be the first piece of the observability stack built**, ahead of dashboards, because a dashboard nobody is actively watching provides no incident-response value, while even minimal alerting (a Slack webhook on a handful of the most severe conditions) provides real value immediately.

## Recommended additional alerts, specific to this platform's confirmed gaps

Beyond the generic table above, this platform's own known failure modes suggest specific alerts worth adding immediately, cheaply, ahead of a full Prometheus/Grafana buildout:

- DLQ depth growing across any of the 4 fragmented DLQ systems (directly addresses `INF-GAP-05`).
- Ledger `is_balanced = FALSE` entries appearing at all (should be zero, always — an alert here is a direct, cheap mitigation for `LS-CRIT-02` even before the underlying validation gap is fixed in code).
- Any webhook signature-verification failure spike (could indicate an attack against the SendGrid gap, `NS-BL-01`, or a legitimate integration break).
- HITL queue items exceeding the 15-minute SLA.

## Related documents

[`35-monitoring-logging.md`](35-monitoring-logging.md), [`../12-operations/41-incident-response-plan.md`](../12-operations/41-incident-response-plan.md), [`../06-api-events/128-retry-dead-letter-strategy.md`](../06-api-events/128-retry-dead-letter-strategy.md).
