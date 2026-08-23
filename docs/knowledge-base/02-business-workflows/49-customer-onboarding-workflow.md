# Customer Onboarding Workflow

**Status:** STABLE — the registration-through-KYC-approval slice of [`05-customer-journey-e2e.md`](05-customer-journey-e2e.md), pulled out as its own workflow document since onboarding is the piece most teams (support, compliance, growth) need in isolation.

## Trigger

A new user opens the app and chooses to register.

## Actors

Customer, Gateway (auth + KYC orchestration), NADRA Verisys, Shufti Pro (or equivalent liveness/OCR vendor), KYC Ops (conditional, manual review).

## Preconditions

None — this is the entry point for every customer.

## Steps

1. Phone number entered → OTP sent (Jazz SMS) → verified within 3 attempts → JWT issued, `users.status = 'pending_kyc'`.
2. CNIC front/back uploaded via S3 presigned URLs.
3. OCR extraction + NADRA Verisys check.
4. Liveness selfie captured, anti-spoofing check run.
5. Face match computed against the CNIC photo.
6. Device fingerprint passively captured.
7. Auto-approve (face match ≥80%) → `users.status = 'active'`, credit scoring triggered. **Or** route to manual review (70–79%) → KYC Ops decision within 24hr SLA. **Or** hard-reject (<70%, or any hard-fail signal).

## Business rules

- No purchase-related action (URL extraction offer, credit check) is available until `users.status = 'active'`.
- A rejected applicant may re-apply after 30 days.
- Manual review decisions are logged to `audit_trails` and require the `compliance_officer` role.

## System services involved

Gateway (owns the entire pipeline), NADRA Verisys and Shufti Pro (external, currently stubbed — see [`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md)).

## Events generated

None published externally today — KYC approval triggers credit scoring via a direct internal call, not a pub/sub event.

## Database changes

`users` (status transition), `user_kyc_verifications` (full record), `user_devices` (fingerprint), `kyc_verification_queue` (if routed to manual review).

## Failure cases

NADRA unavailable → `503 NADRA_UNAVAILABLE`, queued for retry. OCR confidence too low after 2 retries → routed to manual review rather than blocked. Duplicate CNIC on a new account → `duplicate_cnic` rejection code.

## Expected outcome

`users.status = 'active'`, ready to submit a product URL.

## Related documents

[`05-customer-journey-e2e.md`](05-customer-journey-e2e.md), [`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md), [`../16-customer-documentation/62-customer-lifecycle.md`](../16-customer-documentation/62-customer-lifecycle.md).
