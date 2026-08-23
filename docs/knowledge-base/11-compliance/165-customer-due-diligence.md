# Customer Due Diligence (CDD)

> **STATUS: INTERNAL DRAFT.** Describes what the KYC pipeline does today against a CDD framing; not a compliance-approved CDD policy.

## Standard CDD vs. Enhanced Due Diligence (EDD), as currently designed

The platform's KYC tiers map reasonably well onto a standard CDD/EDD distinction: Tier 1 (all users) functions as standard CDD — identity verification (CNIC + NADRA), liveness/face-match. Tier 2 (orders >PKR 5,000 or a fraud flag) functions as EDD — additional bank/wallet connection, income proof, utility bill. See [`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md) for full detail.

## What a formal CDD policy typically requires, and current status against each

| Typical CDD requirement | Current status |
|---|---|
| Identity verification | Designed (NADRA + OCR + liveness), **but vendor integrations are stubs** — not actually performed today |
| Source-of-funds / income verification | Present at Tier 2 (income proof) but no documented policy on what counts as acceptable evidence or how it's verified |
| Sanctions/watchlist screening | Referenced once as a manual-review trigger ("high-risk sanctions watchlist — any match"), mechanism unspecified |
| Politically Exposed Person (PEP) screening | **Not referenced anywhere in current engineering documentation** — a real gap for Compliance to close |
| Ongoing/periodic re-verification (not just at onboarding) | Not documented — CDD is treated as a one-time onboarding event in current design, with no periodic refresh trigger |

## The PEP screening gap specifically

Most CDD frameworks require PEP screening as a distinct control from general sanctions screening — its complete absence from documentation (not even a placeholder reference, unlike sanctions screening) suggests this hasn't been considered yet, not just under-implemented. Recommend Compliance treat this as a new requirement to design, not an existing gap to close.

## Related documents

[`37-kyc-aml-policy.md`](37-kyc-aml-policy.md), [`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md).
