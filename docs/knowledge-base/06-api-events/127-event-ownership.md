# Event Ownership

**Status:** STABLE — who should publish and who should consume each event, consolidated as its own reference since ownership ambiguity is directly implicated in several confirmed gaps.

## Ownership table

| Event | Owner (publisher) | Consumer(s) |
|---|---|---|
| `product.extracted` | Product Service | Gateway |
| `payment.down_payment_confirmed` | Payment Orchestrator | Product Service |
| `vcn.issued` | Payment Orchestrator | Product Service |
| `order.purchase_confirmed` | Product Service | Gateway, Notification Service |
| `delivery_status_changed` / `delivery_confirmed` | Notification Service | Gateway |
| `payment.confirmed` | Payment Orchestrator | Ledger Service |
| `loan.created` | **Gateway (should be — currently publishes nothing)** | Ledger Service |
| `billing.installment_overdue` | **Ledger Service (should be — currently publishes nothing)** | Notification Service |
| `order.cancelled` | **Gateway (should be — currently publishes nothing)** | Notification Service, Payment Orchestrator |
| `vcn.expired` | **Payment Orchestrator (should be — currently publishes nothing)** | Notification Service |
| `kyc.documents_needed` | **Gateway (should be — currently publishes nothing)** | Notification Service |
| `credit.limit_changed` | **Gateway (should be — currently publishes nothing)** | Notification Service |

## Why "ownership" is the right lens for closing these gaps

Every confirmed-missing event above has an unambiguous intended owner — this isn't a case of nobody knowing whose job it is; it's a case of the responsible service simply not having implemented the publish call yet. Framing these as an ownership checklist (rather than a generic "missing events" list) makes each one directly assignable: whoever owns Gateway's contract-signing code owns fixing `loan.created`; whoever owns Ledger's billing sweep owns `billing.installment_overdue`.

## Ownership principle going forward

The service that *causes* a state change owns publishing the event that announces it — a consumer should never be responsible for inferring that something happened by polling or side-channel means. This principle is already followed correctly for the events that do work (e.g., Payment Orchestrator, not Gateway, publishes `payment.down_payment_confirmed`, since Payment Orchestrator is the one that knows payment succeeded) — it should simply be applied consistently to the gaps above.

## Related documents

[`24-event-catalog.md`](24-event-catalog.md), [`../05-architecture/21-service-responsibility-matrix.md`](../05-architecture/21-service-responsibility-matrix.md).
