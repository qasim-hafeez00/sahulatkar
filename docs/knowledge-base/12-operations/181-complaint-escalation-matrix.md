# Complaint Escalation Matrix

**Status:** PLANNED — proposed matrix, since no formal complaints procedure exists yet (see [`../11-compliance/170-complaints-grievance-procedure.md`](../11-compliance/170-complaints-grievance-procedure.md)). This document gives the matrix shape specifically; that document covers the compliance-process requirements around it.

## Proposed matrix

| Level | Owner | Handles | Escalates when |
|---|---|---|---|
| 1 | `cs_agent` (once general support ticketing exists) | General inquiries, order status questions, straightforward "how do I" questions | Customer disputes a charge, alleges an error, or is dissatisfied with a Level 1 answer |
| 2 | `operations_manager` | Order-level intervention, HITL-adjacent issues, service-quality complaints | Complaint touches risk, fraud, compliance, or a financial discrepancy |
| 3 | `credit_risk_analyst` / `fraud_analyst` / `compliance_officer` | Risk holds, KYC decisions, fraud allegations, Shariah-compliance concerns | Complaint implicates a systemic issue (not a one-off) or requires a policy exception |
| 4 | `finance_analyst` | Payment/reconciliation disputes, refund requests | Amount in dispute is large, or the customer is escalating for a second time |
| 5 | Leadership | Anything requiring a policy exception, legal exposure, or a decision no other role is authorized to make | — (top of the ladder) |

This mirrors the general support escalation matrix in [`../02-business-workflows/57-customer-support-escalation-workflow.md`](../02-business-workflows/57-customer-support-escalation-workflow.md) — repeated here specifically framed around *complaints* (which imply dissatisfaction and often a compliance dimension) rather than general inquiries.

## What distinguishes a "complaint" from a general inquiry, for routing purposes

A complaint should be logged with a case ID and tracked toward resolution with an SLA (once the infrastructure exists) — a general inquiry ("where's my order") typically resolves in a single interaction and doesn't need the same tracking rigor. Staff should be trained to recognize the distinction, since under-classifying a real complaint as a routine inquiry would undermine the entire point of having a tracked grievance process.

## Related documents

[`../11-compliance/170-complaints-grievance-procedure.md`](../11-compliance/170-complaints-grievance-procedure.md), [`../02-business-workflows/57-customer-support-escalation-workflow.md`](../02-business-workflows/57-customer-support-escalation-workflow.md).
