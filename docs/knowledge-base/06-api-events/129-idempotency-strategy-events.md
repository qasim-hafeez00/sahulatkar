# Idempotency Strategy (Events)

**Status:** STABLE — the event-specific companion to [`122-idempotency-standards.md`](122-idempotency-standards.md) (which covers API-level idempotency); this document covers the distinct problem of a consumer processing the same event twice.

## Why event idempotency is a distinct problem from API idempotency

Redis Pub/Sub gives no exactly-once delivery guarantee — a subscriber can, in principle, receive the same message more than once (e.g., during a reconnect), or a publisher retrying after an ambiguous failure could publish the "same" logical event twice. A consumer that isn't idempotent to this will double-process — e.g., posting a GL entry twice for one payment confirmation.

## Current state

No documented event-level deduplication mechanism exists (e.g., an event ID uniqueness check before a consumer acts on it) — this is a gap on top of the payload-schema-validation gap noted in [`126-event-schema.md`](126-event-schema.md); both trace back to `build_event_envelope()` not doing enough at the publish/consume boundary.

## Recommended pattern

Every event should carry a unique event ID (not just a timestamp) in its envelope. Every consumer that has a side effect (writing to a database, calling another service) should check "have I already processed this event ID" before acting — a simple Redis `SETNX`-based dedup check, or a dedicated `processed_events` table, would suffice. This mirrors the API-level idempotency-key pattern recommended in [`122-idempotency-standards.md`](122-idempotency-standards.md) — same underlying discipline, applied at the event-consumption boundary instead of the API-request boundary.

## Concrete risk this addresses

Ledger Service consuming `payment.confirmed` twice (e.g., due to a Redis reconnect replay) would currently double-post a GL entry, directly compounding the debit=credit invariant gap already documented in [`../20-ledger-accounting/113-ledger-invariants.md`](../20-ledger-accounting/113-ledger-invariants.md) — these gaps interact, not just coexist.

## Related documents

[`122-idempotency-standards.md`](122-idempotency-standards.md), [`126-event-schema.md`](126-event-schema.md), [`../20-ledger-accounting/113-ledger-invariants.md`](../20-ledger-accounting/113-ledger-invariants.md).
