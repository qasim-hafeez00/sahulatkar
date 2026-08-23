# Complaints / Grievance Procedure

> **STATUS: INTERNAL DRAFT — no procedure exists.** This mirrors the gap already noted in [`../12-operations/39-customer-support-sop.md`](../12-operations/39-customer-support-sop.md); this document adds the compliance-specific framing (why a *regulated* complaints procedure is a distinct requirement from general customer support).

## Why this is a compliance requirement, not just an operations nicety

Consumer-lending regulatory frameworks (referenced generally in `docs/Sahulatkar-docs/` research, and implied by SECP's general fair-treatment expectations) typically require a **documented, auditable** complaints process — not just "customers can contact support somehow." This usually means: a defined intake channel, a logged case with a tracked status, a maximum response-time SLA, an escalation path if the customer is unsatisfied with the first response, and a periodic report to leadership/regulators on complaint volume and themes.

## Current state

None of this exists. General support ticketing itself is unbuilt (AD-14/AD-15, per [`../12-operations/39-customer-support-sop.md`](../12-operations/39-customer-support-sop.md)) — meaning even the basic infrastructure a compliant grievance procedure would need doesn't exist yet, let alone the compliance-specific process wrapped around it.

## Recommended design, once general support ticketing exists

1. Every complaint gets a tracked case ID, regardless of channel (phone, WhatsApp, in-app).
2. A defined SLA (e.g., acknowledged within 24 hours, resolved or escalated within 7 days) — no such SLA currently exists anywhere in engineering docs, unlike the KYC (24hr) and HITL (15min) SLAs which are well-specified.
3. A distinction between a general service complaint and a complaint that touches Shariah compliance or fair-treatment/consumer-protection specifically — the latter should route to Compliance directly, not just Ops, and should feed [`19-shariah-review-register.md`](../04-shariah/19-shariah-review-register.md) or [`36-compliance-requirements-matrix.md`](36-compliance-requirements-matrix.md) if it surfaces a real gap.
4. Periodic (e.g., quarterly) reporting of complaint themes to leadership — connects to [`173-compliance-monitoring.md`](173-compliance-monitoring.md).

## Related documents

[`../12-operations/39-customer-support-sop.md`](../12-operations/39-customer-support-sop.md), [`168-consumer-protection-policy.md`](168-consumer-protection-policy.md), [`173-compliance-monitoring.md`](173-compliance-monitoring.md).
