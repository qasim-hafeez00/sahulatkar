# KYC Escalation SOP

**Status:** STABLE — the operational SOP companion to [`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md), written for the `compliance_officer` doing the actual review rather than the engineer maintaining the pipeline.

## When an item reaches you

An application routes to the manual queue when: face match is 70–79%, NADRA name mismatch is 10–20%, OCR confidence stayed below 85% after 2 retries, document tampering was flagged, or a watchlist match occurred. SLA: 24 hours from queue entry.

## What to check

1. Review the CNIC images, selfie, and the specific flag that routed this item (don't just re-run the automated checks mentally — look at *why* it was borderline).
2. For a watchlist match specifically: confirm whether it's a genuine match or a common-name false positive before any further action — this determines whether the case needs escalation beyond a simple approve/reject.
3. For document tampering flags: treat as higher-scrutiny than a simple confidence-score borderline case — this may warrant escalation to Fraud rather than a routine KYC decision.

## Decision

`POST /admin/kyc/{id}/decision` — approve or reject with a reason code. Approval triggers credit scoring automatically.

## Known process gap to work around manually

No SLA-breach alerting exists (`GW-BL-08`) — until this is built, whoever owns the KYC queue should manually check for items approaching or past the 24-hour SLA rather than relying on the system to flag them.

## Escalation beyond this SOP

Watchlist matches confirmed as genuine, or tampering flags confirmed as real fraud attempts, should escalate to the fraud investigation process — see [`../18-credit-risk-policy/95-fraud-investigation-workflow.md`](../18-credit-risk-policy/95-fraud-investigation-workflow.md) — rather than being closed out as a routine KYC rejection.

## Related documents

[`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md), [`178-fraud-escalation-sop.md`](178-fraud-escalation-sop.md).
