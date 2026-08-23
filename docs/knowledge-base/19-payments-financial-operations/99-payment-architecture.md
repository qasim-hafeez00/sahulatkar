# Payment Architecture

**Status:** STABLE — the architectural view of Payment Orchestrator, complementing [`../05-architecture/microservices/payment-orchestrator.md`](../05-architecture/microservices/payment-orchestrator.md) (service-level) and [`../02-business-workflows/08-payment-workflow.md`](../02-business-workflows/08-payment-workflow.md) (workflow-level) with the integration/routing layer specifically.

## Gateway adapter pattern

Each payment method (Safepay, JazzCash, EasyPaisa, Raast) is implemented as an independent adapter behind a common interface, allowing the routing engine to select a gateway per-transaction without the calling code needing method-specific branching. This is why adding Raast (Phase 4) is additive rather than requiring a rewrite of the payment flow.

## Routing engine

Selects a payment method based on: what the customer chose in the UI, operator detection (Jazz/Telenor/Zong/Ufone via phone prefix), and — per a documented fix referenced in the audit ("GAP-07 FIX: Prioritize Raast if valid mandate exists") — an intended preference for Raast when a valid recurring-payment mandate exists. **Known gap:** Raast mandate lookup itself is not fully implemented (`PO-CRIT-03`), so this prioritization currently has no live data to act on.

## Synchronous vs. asynchronous gateway flows

Safepay uses an async redirect flow (user leaves the app, pays on Safepay's hosted page, returns) — this requires the return-URL/webhook combination to be correctly wired, and per the audit, the **post-payment redirect URL for Safepay is not currently configured** (a real, specific integration gap, not just a general note). JazzCash and EasyPaisa are synchronous direct-API charges — no redirect needed, response comes back in the same request/response cycle.

## Internal architecture: VCN as a payment instrument, not just a card

The single-use VCN (see [`../03-bnpl-financing/16-financing-state-machine.md`](../03-bnpl-financing/16-financing-state-machine.md) for its state machine) is architecturally a *separate* payment rail from the customer-facing gateways above — it's the instrument Payment Orchestrator issues *to itself* (via Stripe Issuing) for the checkout agent to spend against a third-party merchant, distinct from how it collects money *from* the customer. Understanding this separation matters: a bug in customer-collection (e.g., Safepay webhook handling) and a bug in VCN spend (e.g., issuer-side void failure) are architecturally independent failure domains, even though both live in Payment Orchestrator.

## Related documents

[`../05-architecture/microservices/payment-orchestrator.md`](../05-architecture/microservices/payment-orchestrator.md), [`../02-business-workflows/08-payment-workflow.md`](../02-business-workflows/08-payment-workflow.md), [`100-payment-lifecycle.md`](100-payment-lifecycle.md).
