# Event Ordering Rules

**Status:** STABLE — no ordering guarantee currently exists; this document states that plainly and identifies where it matters.

## Current guarantee: none

Redis Pub/Sub provides no cross-subscriber ordering guarantee, and nothing in the platform's event-handling code is documented as compensating for out-of-order delivery (e.g., via sequence numbers or vector clocks).

## Where ordering actually matters in this platform

| Event pair | Why order matters | Currently protected? |
|---|---|---|
| Wakalah signed → Murabaha signed | Murabaha should never be generated before Wakalah is confirmed signed | **No** — enforced (weakly) only by a record-existence check, not a signed-state check (`GW-BL-03`) |
| `payment.down_payment_confirmed` → `vcn.issued` | VCN must never be issued before payment is confirmed | Enforced by the hard-gate design (VCN issuance is triggered *by* the confirmation event, not raced against it) — this ordering is structurally correct by construction |
| `order.purchase_confirmed` → delivery tracking registration | Shouldn't register a shipment before a purchase is confirmed | Not independently verified |
| `vcn.issued` → `order.cancelled` (race noted in the audit) | If cancellation happens while checkout is already starting, an in-flight purchase could proceed on a cancelled order | **Confirmed race condition** (`PS-BL-06`) — the checkout consumer doesn't have a documented way to check for a last-moment cancellation before proceeding |

## Why "no ordering guarantee" combined with "some sequences require order" is a real design tension

The platform mostly avoids ordering problems by structural design (an event is *triggered by* the state it depends on, so causality is naturally preserved for most pairs) — but the two rows above marked with gaps show where this design principle either wasn't fully applied (Wakalah/Murabaha) or where a genuine race window exists despite good intentions (VCN-issued vs. cancellation). Recommend Engineering audit every event-triggered transition for this same causality-vs-race distinction, since the pattern that caused these two gaps could exist elsewhere undetected.

## Related documents

[`24-event-catalog.md`](24-event-catalog.md), [`../03-bnpl-financing/16-financing-state-machine.md`](../03-bnpl-financing/16-financing-state-machine.md).
