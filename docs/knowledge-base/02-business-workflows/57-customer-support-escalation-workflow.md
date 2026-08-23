# Customer Support Escalation Workflow

**Status:** PLANNED — mirrors the gap noted in [`../12-operations/39-customer-support-sop.md`](../12-operations/39-customer-support-sop.md): no general support-ticketing system is implemented. This document describes the target escalation flow once AD-14/AD-15 (Customer Support — Tickets) exist, and the two working queues that already function as de facto escalation paths.

## What escalates today, and how

| Issue type | Escalation path | SLA |
|---|---|---|
| KYC borderline/failed | Auto-routed to manual review queue | 24 hours |
| Checkout automation stuck | Auto-routed to HITL queue | 15 minutes |
| Everything else | **No documented path** — see [`../12-operations/39-customer-support-sop.md`](../12-operations/39-customer-support-sop.md) | N/A |

## Target design (once general ticketing exists)

```
Customer raises an issue
  → Level 1: cs_agent — general inquiries, order status, read-only account view
    → Level 2: operations_manager — order-level intervention, HITL-adjacent issues
      → Level 3: credit_risk_analyst / fraud_analyst / compliance_officer — risk holds, KYC, compliance
        → Level 4: finance_analyst — payment/reconciliation disputes
          → Level 5: leadership — policy exception or legal exposure
```

This mirrors the RBAC role structure already defined for admin access (see [`../08-security/29-authentication-authorization.md`](../08-security/29-authentication-authorization.md)) — the escalation ladder should follow the same role boundaries rather than inventing a separate one.

## Trigger

Any customer-initiated contact that isn't automatically resolved by the KYC or HITL queues above.

## Known hard limitation for support staff today

Refunds cannot currently be executed through the system at all (`RefundOrchestrator` is a stub) — any escalation that would normally resolve with "we'll refund you" currently has no system-supported resolution path. Support staff need an honest, documented manual fallback until this is fixed. See [`09-refund-cancellation-workflow.md`](09-refund-cancellation-workflow.md).

## Related documents

[`../12-operations/39-customer-support-sop.md`](../12-operations/39-customer-support-sop.md), [`../12-operations/41-incident-response-plan.md`](../12-operations/41-incident-response-plan.md).
