# Data Protection Compliance

> **STATUS: INTERNAL DRAFT.**

## What's implemented (technical controls)

Column-level encryption for CNIC/IBAN/VCN/MFA secrets (`pgcrypto` AES-256), data residency confined to AWS `ap-south-1`, S3 server-side encryption for KYC images with lifecycle transition to Glacier after 1 year. See [`../08-security/139-encryption-standard.md`](../08-security/139-encryption-standard.md).

## What's missing (policy and process, not technical controls)

- **No documented Data Protection Policy** covering: what data is collected and why, who can access it internally (beyond the general RBAC field-level examples in [`../08-security/29-authentication-authorization.md`](../08-security/29-authentication-authorization.md)), what third parties data is shared with (NADRA, Shufti Pro, payment gateways — all receive customer PII, none of these data-sharing relationships are documented from a data-protection-compliance angle specifically).
- **No Data Subject Request procedure** — if a customer asks "what data do you have on me" or "delete my data," there's no documented process to fulfill that request, and given the platform's 7-year NADRA-retention citation and general audit-trail requirements, a deletion request would need to reconcile against those retention obligations rather than being a simple blanket delete.
- **No Data Classification Policy** — while encryption is applied to specific fields (CNIC, IBAN, VCN, MFA secrets), there's no documented classification scheme (e.g., "restricted," "confidential," "internal") that would tell an engineer adding a *new* sensitive field whether it needs the same treatment, absent someone remembering to apply the existing pattern by convention.
- **No Data Breach Response procedure with defined notification obligations** — see [`../12-operations/41-incident-response-plan.md`](../12-operations/41-incident-response-plan.md), which flags this same gap from the incident-response angle.

## Related documents

[`../08-security/139-encryption-standard.md`](../08-security/139-encryption-standard.md), [`171-record-retention-policy.md`](171-record-retention-policy.md), [`../12-operations/41-incident-response-plan.md`](../12-operations/41-incident-response-plan.md).
