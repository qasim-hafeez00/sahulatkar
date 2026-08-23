# Customer Support SOP

**Status:** PLANNED for general support ticketing (not yet built) · STABLE for the two queues that do exist (KYC manual review, checkout HITL).

## What exists today

SahulatKar has two functioning "support" queues, both operational/technical rather than a traditional customer-support ticketing system:

### KYC manual review queue

- **SLA:** 24 hours.
- **Trigger:** borderline KYC results (face match 70–79%, NADRA name mismatch 10–20%, low OCR confidence after retries) — see [`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md).
- **Role:** `compliance_officer` decides approve/reject via `POST /admin/kyc/{id}/decision`, logged to `audit_trails`.
- **Known gap:** no SLA-breach alerting exists if an item sits unclaimed or undecided past 24/48 hours (`GW-BL-08`).

### Checkout HITL (Human-in-the-Loop) queue

- **SLA:** 15 minutes from escalation.
- **Trigger:** the checkout agent fails to complete a purchase automatically (CAPTCHA, bot detection, 3DS, out-of-stock, repeated failure) — see [`../05-architecture/microservices/product-service.md`](../05-architecture/microservices/product-service.md).
- **Role:** `operations_manager`, via `GET/POST /admin/hitl/...` — claim, resolve (with a resolution code: `manual_purchase_completed`, `cancelled_refund`, `customer_contacted`, `alternative_offered`), or take remote control of the live browser session mid-checkout.
- **Known gap:** since a large portion of automated checkout currently fails outright (`PS-BL-03`), this queue is likely to see disproportionately high volume relative to what its 15-minute SLA and staffing were probably sized for once the platform handles real order volume — flag for Ops capacity planning ahead of any volume increase.

## What is speced but not built

The full admin support-ticketing system (AD-14 "Customer Support — Tickets," AD-15 "Ticket Detail Split View") appears in the 20-module admin dashboard plan (`docs/System-md-files/M10-M12-delivery-ledger-admin.md`) but **has no corresponding backend implementation** per the code audit (`GW-GAP-16`) — there is currently no general-purpose support ticket system for issues outside the two queues above (e.g., "my delivery is late," "I was charged twice," "I want to dispute a purchase").

## Recommended interim process (until ticketing is built)

Given the gap above, and until AD-14/AD-15 ship:

1. Route general customer inquiries through whatever channel currently exists outside the product (phone, WhatsApp business number, email) — not documented in engineering docs, since this is an operational/business decision rather than a technical one.
2. For anything payment- or refund-related, be aware that refunds are **not currently implementable through the system at all** (see [`../02-business-workflows/09-refund-cancellation-workflow.md`](../02-business-workflows/09-refund-cancellation-workflow.md)) — support staff need an honest, documented fallback process (manual reconciliation, manual gateway refund) until `RefundOrchestrator` is built, rather than promising a refund the system can't yet execute.
3. For order-status confusion caused by known cross-service gaps (e.g., a payment captured but order status not updated — see [`../02-business-workflows/07-bnpl-workflow-e2e.md`](../02-business-workflows/07-bnpl-workflow-e2e.md)), support staff need direct database/admin visibility into the true state, since the customer-facing status may be stale.

## Escalation matrix (target design, adapted from RBAC roles — not yet formalized as an explicit support escalation policy)

| Level | Owner | Scope |
|---|---|---|
| 1 | `cs_agent` (once built) | General inquiries, order status, read-only account view |
| 2 | `operations_manager` | HITL resolution, order-level intervention |
| 3 | `credit_risk_analyst` / `fraud_analyst` / `compliance_officer` | Risk holds, KYC decisions, compliance issues |
| 4 | `finance_analyst` | Payment/reconciliation disputes |
| 5 | Leadership | Anything requiring policy exception or legal exposure |

## Related documents

[`40-merchant-vendor-support-sop.md`](40-merchant-vendor-support-sop.md), [`41-incident-response-plan.md`](41-incident-response-plan.md), [`../02-business-workflows/09-refund-cancellation-workflow.md`](../02-business-workflows/09-refund-cancellation-workflow.md).
