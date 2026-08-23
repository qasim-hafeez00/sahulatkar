# Credit / Eligibility Workflow

**Status:** STABLE — workflow-format companion to [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md), which remains authoritative for the actual scoring rules.

## Trigger

A KYC-approved user's product offer requires a credit decision (i.e., every offer generation, not just first-time onboarding).

## Actors

Customer (indirectly), Gateway, Credit Engine.

## Preconditions

`users.status = 'active'`, product successfully extracted with a known price.

## Steps

1. Gateway calls `GET /credit/check` with the user ID and order amount.
2. Credit Engine runs Layers 1–7 in sequence (hard blocks → velocity → identity/device → alternative data → ML scoring → category overlay → portfolio controls), short-circuiting on any hard block.
3. A risk band (A–F), approved limit, and down-payment percentage are returned within the 3-second SLA.
4. Gateway uses this to construct the financing offer.

## Business rules

Full detail: [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md) and [`15-credit-limit-rules.md`](../03-bnpl-financing/15-credit-limit-rules.md). Key rule for this workflow specifically: a decision is made **fresh on every order**, not cached from onboarding — meaning a user's eligibility can change order to order based on velocity, current utilization, and order-specific category risk.

## System services involved

Credit Engine (owns the decision), Gateway (orchestrates the call and consumes the result).

## Known gap affecting this workflow

`available_credit` is not decremented at order initiation (`GW-BL-01`) — meaning this workflow can currently approve two concurrent orders that together exceed a user's actual limit, since each is evaluated independently against the same un-decremented figure. See [`../03-bnpl-financing/15-credit-limit-rules.md`](../03-bnpl-financing/15-credit-limit-rules.md).

## Expected outcome

Approve (offer proceeds), decline (order ends, reason shown), or manual review (order paused pending risk analyst decision).

## Related documents

[`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md), [`../05-architecture/microservices/credit-engine.md`](../05-architecture/microservices/credit-engine.md).
