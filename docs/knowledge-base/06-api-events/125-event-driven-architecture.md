# Event-Driven Architecture

**Status:** STABLE — the architectural-pattern view; [`24-event-catalog.md`](24-event-catalog.md) remains authoritative for the actual event list.

## Why event-driven, and where

Redis Pub/Sub is used specifically for cross-service **state synchronization** where the publishing service shouldn't need to know or care who's listening (e.g., Payment Orchestrator publishing `payment.down_payment_confirmed` without needing to know Product Service is the one that'll act on it). This is distinct from the platform's other two communication patterns — synchronous internal REST (for calls that need an immediate answer, like a credit check) and Redis-backed queues/BullMQ (for durable background work like checkout automation) — see [`../05-architecture/20-system-architecture.md`](../05-architecture/20-system-architecture.md).

## The architectural bet this pattern makes, and where it's failing

Event-driven architecture trades tight coupling for eventual consistency — the bet is that services can evolve independently as long as the events connecting them are reliable. **This bet is currently not paying off for at least one critical event**: `loan.created` is never published, meaning the architecture's central premise (services stay in sync via events) has a confirmed hole at its most financially important junction. See [`24-event-catalog.md`](24-event-catalog.md) for the full list of confirmed-missing events.

## Choice of Redis Pub/Sub over a durable message broker

See ADR-005 in [`../14-project-management/44-architecture-decision-records.md`](../14-project-management/44-architecture-decision-records.md) for the reasoning and the trade-off this implies (no durable delivery guarantee for offline subscribers) — directly relevant to why several "should be published" events in the catalog simply aren't reliably delivered even when they are published.

## Related documents

[`24-event-catalog.md`](24-event-catalog.md), [`../14-project-management/44-architecture-decision-records.md`](../14-project-management/44-architecture-decision-records.md) (ADR-005).
