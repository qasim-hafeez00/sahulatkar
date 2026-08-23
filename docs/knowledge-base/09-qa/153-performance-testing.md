# Performance Testing

**Status:** PLANNED — explicit Phase 4 target (k6, 1,000 concurrent users) per `docs/MASTER_PLAN.md` §8, not yet conducted.

## SLA targets that performance testing must validate

| SLA | Target | From |
|---|---|---|
| Credit decision | <3s p99 | [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md) |
| Billing sweep | 100K rows processed in <60s | [`../07-database/25-database-architecture.md`](../07-database/25-database-architecture.md), relies on the critical partial index |
| KYC Tier 1 | <4 minutes end to end | [`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md) |
| HITL resolution | <15 minutes | [`../12-operations/39-customer-support-sop.md`](../12-operations/39-customer-support-sop.md) |

## Load testing plan

k6 scripts targeting 1,000 concurrent users — not yet built. Should specifically stress-test the credit-check path (Layer 4's external JazzCash API call is the largest single latency budget item in the 7-layer pipeline, per [`../18-credit-risk-policy/88-eligibility-engine-specification.md`](../18-credit-risk-policy/88-eligibility-engine-specification.md), and therefore the most likely bottleneck under load) and the billing sweep's critical index (confirm the "100K rows in <60s" claim actually holds at real data volumes, not just as a documented target).

## Database connection pool testing

PgBouncer is sized for 2,000 client connections down to 180 PostgreSQL connections (see [`../07-database/25-database-architecture.md`](../07-database/25-database-architecture.md)) — load testing should specifically verify this sizing holds under the target 1,000-concurrent-user load without connection exhaustion, since a pool-exhaustion failure mode under load is a common and easily-missed production surprise.

## KEDA autoscaling testing

The checkout agent's 0→100 pod autoscaling (queue-depth driven) should be load-tested specifically for scale-up latency — how quickly does capacity actually respond to a queue-depth spike, and does the scale-up keep pace with realistic order-volume bursts (e.g., a marketing campaign driving a sudden influx)?

## Related documents

[`../10-devops/33-infrastructure-architecture.md`](../10-devops/33-infrastructure-architecture.md), [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md).
