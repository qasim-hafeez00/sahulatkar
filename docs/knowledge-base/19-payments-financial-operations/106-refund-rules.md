# Refund Rules

**Status:** PLANNED — no refund rules exist because no refund mechanism exists. This document proposes rules for when `RefundOrchestrator` is built, given the design context established in [`../02-business-workflows/09-refund-cancellation-workflow.md`](../02-business-workflows/09-refund-cancellation-workflow.md).

## Proposed refund amount rules

| Scenario | Proposed refund amount |
|---|---|
| Cancellation before down payment collected | N/A — nothing to refund |
| Cancellation after down payment, before purchase execution | Full down payment |
| Purchase failed (out of stock, checkout failure, HITL exhausted) | Full down payment |
| Product returned, merchant accepts return | Amount the merchant actually refunded, potentially minus a documented restocking/handling policy (not yet decided) |
| Product returned, merchant refuses | **Open policy question** — see [`../02-business-workflows/09-refund-cancellation-workflow.md`](../02-business-workflows/09-refund-cancellation-workflow.md) |

## Proposed refund method

Refund to the original payment method where the gateway supports it (Safepay/JazzCash/EasyPaisa typically support refunding to the originating instrument) — this should be the default rule rather than, e.g., issuing platform credit, since the customer paid real money via a real instrument.

## What must exist before any refund rule can actually be enforced

`RefundOrchestrator.initiate_refund()` implementation, VCN void wired to `order.cancelled`, and a Ledger `refund` journal entry type actually exercised in code (the schema supports it; nothing currently triggers it) — see [`../02-business-workflows/09-refund-cancellation-workflow.md`](../02-business-workflows/09-refund-cancellation-workflow.md) for the full build checklist.

## Related documents

[`../02-business-workflows/09-refund-cancellation-workflow.md`](../02-business-workflows/09-refund-cancellation-workflow.md), [`107-reversal-rules.md`](107-reversal-rules.md).
