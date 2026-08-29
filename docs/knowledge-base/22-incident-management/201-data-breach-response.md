# Data Breach Response

**Status:** PLANNED — no data breach response procedure exists in current documentation, despite the platform holding CNIC, KYC images, and payment-card data. This mirrors the gap already noted in [`../12-operations/41-incident-response-plan.md`](../12-operations/41-incident-response-plan.md) and [`../11-compliance/169-data-protection-compliance.md`](../11-compliance/169-data-protection-compliance.md); this document is the dedicated incident-management-category version.

## Proposed response phases

1. **Detect and contain** — identify the scope (which data, how many customers, how it happened), stop the ongoing exposure if still active.
2. **Assess** — what data was actually exposed (CNIC? VCN details? just contact info?) — the encrypted fields (CNIC, VCN, MFA secrets — see [`../08-security/139-encryption-standard.md`](../08-security/139-encryption-standard.md)) being exposed as ciphertext is a materially different severity than the encryption key or plaintext being exposed; this distinction should drive the response, not be glossed over.
3. **Notify** — both regulatory (obligations currently unconfirmed, see [`../11-compliance/36-compliance-requirements-matrix.md`](../11-compliance/36-compliance-requirements-matrix.md) and [`../11-compliance/169-data-protection-compliance.md`](../11-compliance/169-data-protection-compliance.md)) and affected customers. **Neither notification path is currently defined anywhere in this repository** — this is a genuine gap Legal/Compliance needs to close before it's needed under pressure.
4. **Remediate** — close the vulnerability, rotate any credentials that could have contributed (directly dependent on the secret-rotation mechanism still being built, per [`../08-security/138-secrets-management.md`](../08-security/138-secrets-management.md)).
5. **Post-incident review** — per [`202-postmortem-template.md`](202-postmortem-template.md).

## Why this is a genuinely urgent gap, not a theoretical one

Given the platform holds exactly the kind of data (national ID, biometric selfies, payment card details) that makes it a high-value target, and given several confirmed security gaps already exist in this codebase (unrated-limited VCN-decrypt endpoint, no admin TOTP lockout, unauthenticated SendGrid webhook — see [`../08-security/140-security-threat-model.md`](../08-security/140-security-threat-model.md)), the absence of a breach-response plan is a materially higher-priority gap here than it would be for a platform with a cleaner security posture and less sensitive data.

## Related documents

[`../11-compliance/169-data-protection-compliance.md`](../11-compliance/169-data-protection-compliance.md), [`../08-security/140-security-threat-model.md`](../08-security/140-security-threat-model.md), [`../12-operations/41-incident-response-plan.md`](../12-operations/41-incident-response-plan.md).
