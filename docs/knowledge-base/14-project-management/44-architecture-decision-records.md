# Architecture Decision Records (ADRs)

**Status:** STABLE as a **backfilled** set — these ADRs were reconstructed from evident architecture choices in the codebase and engineering docs, not from original decision records (none exist yet in this repository). Each is written as inferred rationale; where the actual original reasoning differs, whoever made the call should correct these rather than treat them as historically authoritative.

## ADR-001: Vendor-agnostic (URL-based) model instead of merchant-network integration

**Decision:** Build a universal product-URL-to-purchase pipeline rather than integrating with individual merchants.
**Rationale (inferred):** Merchant-network BNPL caps coverage at whichever merchants integrate; a vendor-agnostic model provides universal coverage from day one, at the cost of no merchant relationship, cooperation, or guaranteed API stability. See [`../02-business-workflows/06-merchant-vendor-journey.md`](../02-business-workflows/06-merchant-vendor-journey.md) for the operational tradeoffs this creates.
**Status:** Implemented, core to the product.

## ADR-002: Agency Murabaha (Wakalah + Murabaha) instead of a conventional interest-bearing loan

**Decision:** Structure financing as two sequential Shariah contracts rather than a simple loan-with-interest.
**Rationale (inferred):** Required for the product to be Shariah-compliant and to serve observant Muslim consumers, per the "Shariah-structured" positioning in [`../01-company-product/01-product-overview.md`](../01-company-product/01-product-overview.md).
**Status:** Implemented; markup tiering not yet Shariah-board-approved (open item, see [`../04-shariah/19-shariah-review-register.md`](../04-shariah/19-shariah-review-register.md)).

## ADR-003: Microservices (6 services) instead of a monolith

**Decision:** Split Gateway, Product Service, Credit Engine, Payment Orchestrator, Ledger Service, and Notification Service into independently deployable FastAPI services.
**Rationale (inferred):** Clean domain boundaries (identity, catalog/automation, risk, finance-execution, finance-truth, comms) that scale independently — the checkout agent in particular needs to scale 0→100 pods on a completely different cadence than, say, the Ledger Service. Domain-Driven Design with bounded contexts is stated explicitly as the architectural style in `docs/audits/global_system_audit.md`.
**Trade-off incurred:** cross-service consistency now depends on events/callbacks working correctly — and per `docs/PRODUCTION_GAPS_REPORT.md`, several of those links are currently broken (missing `loan.created`, uncompensated payment-confirmation transactions). A monolith wouldn't have eliminated the underlying bugs, but would have made the "two writes need to agree" problem a single-transaction problem instead of a cross-service-event problem.
**Status:** Implemented.

## ADR-004: PostgreSQL as the single system of record, shared across services

**Decision:** One PostgreSQL 16 instance, with per-service table ownership enforced by convention rather than physical database separation.
**Rationale (inferred):** Simpler operationally at current scale than per-service databases, while DDD bounded contexts are still respected at the code/ownership level (see [`../05-architecture/21-service-responsibility-matrix.md`](../05-architecture/21-service-responsibility-matrix.md)). `DECIMAL(14,2)` for all monetary fields and dual BIGSERIAL/UUID keys are consistent platform-wide rules that would be harder to enforce consistently across genuinely separate databases.
**Status:** Implemented.

## ADR-005: Redis Pub/Sub + BullMQ for cross-service events, instead of a dedicated message broker (Kafka, RabbitMQ)

**Decision:** Use Redis for both caching and event distribution rather than adopting a dedicated event-streaming platform.
**Rationale (inferred):** Redis is already required for caching, sessions, and rate limiting — reusing it for pub/sub avoids adding a new piece of infrastructure at current scale.
**Trade-off incurred:** Redis Pub/Sub has no durable delivery guarantee for subscribers who aren't listening at publish time, and no built-in schema enforcement — both cited as contributing factors in the missing-event gaps documented in [`../06-api-events/24-event-catalog.md`](../06-api-events/24-event-catalog.md). If cross-service event reliability remains a recurring source of production bugs, this decision is the first architectural lever worth revisiting (e.g., moving critical financial events like `loan.created` onto a durable queue rather than best-effort pub/sub).
**Status:** Implemented.

## ADR-006: Single-use, MCC-locked VCN per order instead of a shared/reusable purchasing card

**Decision:** Issue a fresh virtual card per order, capped at cost+5%, MCC-restricted, auto-expiring in 24 hours.
**Rationale (inferred):** Minimizes blast radius of a compromised card (single-use, amount-capped) and enforces the "collect first, then buy" sequencing structurally — a card literally cannot exist before payment and contract signing gate its issuance. Also plausibly mitigates the merchant-pattern-detection risk noted in general BNPL research (a distinct card per transaction is harder to fingerprint as automated purchasing than a single reused card).
**Status:** Implemented; issuer-side void-on-expiry not fully wired (`PO-CRIT-04`).

## ADR-007: AWS `ap-south-1` as the sole deployment region

**Decision:** Single-region deployment, no multi-region redundancy at this stage.
**Rationale (inferred):** Data-residency requirement (cited against PECA 2016 — see [`../11-compliance/36-compliance-requirements-matrix.md`](../11-compliance/36-compliance-requirements-matrix.md)) effectively requires staying within a Pakistan-adjacent region regardless of redundancy preferences; single-region keeps initial infrastructure cost/complexity down.
**Status:** Implemented. Multi-region active-active is an explicit Phase 5 (future) item, not current-state.

## Related documents

[`43-product-roadmap.md`](43-product-roadmap.md), [`../05-architecture/20-system-architecture.md`](../05-architecture/20-system-architecture.md).

## Going forward

New ADRs should be added here **at decision time**, not backfilled — the value of an ADR is capturing the actual alternatives considered and the actual reasoning in the moment, which none of the seven above can fully claim to do since they're reconstructed after the fact.
