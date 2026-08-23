# Retry / Dead Letter Strategy

**Status:** STABLE (what exists) — fragmentation and monitoring gaps are the central finding.

## What exists

At least 4 independent dead-letter-queue (DLQ) systems: scraping (Product Service), checkout (Product Service), notification (Notification Service), and ledger events (Ledger Service) — each built separately rather than sharing a common DLQ pattern.

## Retry behavior per system

| System | Retry behavior |
|---|---|
| Scraping | `attempt_number`/`max_attempts` (default 3) tracked per `scraping_jobs` row, then HITL escalation |
| Checkout | Distributed lock with a 600s expiry; **known gap:** if the consumer crashes mid-job, the job isn't re-queued and the execution record stays stuck in `RUNNING` (`PS-BL-05`) |
| Notification | Referenced (`retry_service.py`) but the exact strategy (exponential backoff, max attempts before DLQ) is not documented/verified (`NS-BL-10`) |
| Ledger events | **No consumer processes the DLQ at all** (`LS-CRIT-05`) — failed events accumulate indefinitely |

## The core gap: no unified monitoring

None of the four DLQs above are monitored or alerted on as a group (`INF-GAP-05`) — an item silently stuck in any of them may never be noticed. This is a direct consequence of the broader observability gap documented in [`../10-devops/35-monitoring-logging.md`](../10-devops/35-monitoring-logging.md).

## Recommended consolidation

Rather than four independent DLQ implementations, a shared DLQ pattern in `sk_shared` (consistent structure, consistent retry/backoff policy, consistent Prometheus metric for queue depth) would let a single Grafana panel/alert cover all four — this is a good candidate for the same kind of consolidation already recommended for HMAC verification and pagination in [`../05-architecture/21-service-responsibility-matrix.md`](../05-architecture/21-service-responsibility-matrix.md).

## Related documents

[`24-event-catalog.md`](24-event-catalog.md), [`../10-devops/35-monitoring-logging.md`](../10-devops/35-monitoring-logging.md).
