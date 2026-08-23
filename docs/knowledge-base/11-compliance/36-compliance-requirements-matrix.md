# Compliance Requirements Matrix

> **STATUS: INTERNAL DRAFT.** This document summarizes regulatory bodies and obligations *as referenced in internal engineering documentation* (`docs/System-md-files/00Sahulatkar-System.md`'s "REGULATORY" table and related module specs). It is **not a legal opinion**, not a licensing filing, and has not been reviewed by qualified Pakistani fintech/financial-services counsel. **SahulatKar's actual license/registration status with SECP is not recorded anywhere in this repository** as of this writing — every row below should be treated as "engineering's understanding of what applies," not as confirmed legal fact, until Legal signs off.

## Requirement matrix

| Requirement | Regulator | Applicable product area | Owner (proposed — confirm) | Status |
|---|---|---|---|---|
| NBFC license or Regulatory Sandbox admission | SECP | The financing product itself (Murabaha-structured BNPL) | Legal/Compliance | **Unconfirmed — no license/sandbox status recorded in this repo** |
| Islamic Finance Guidelines 2023 compliance | SECP | Wakalah + Murabaha contract structure | Legal + Shariah Board | **Unconfirmed** — see [`../04-shariah/17-shariah-product-structure.md`](../04-shariah/17-shariah-product-structure.md) open items |
| SECP NBFC Circular 15/2022 (cited as the basis for SHAP credit-decision explainability) | SECP | Credit Engine decision explanations | Credit/Risk | **Citation not independently verified against current SECP text** — confirm applicability to SahulatKar's specific licensing category |
| Monthly RCD-1 reporting | SBP (State Bank of Pakistan) | Financial/regulatory reporting | Finance/Compliance | **Unconfirmed — no reporting pipeline referenced in engineering docs** |
| AML/CFT program | SBP | Customer onboarding, transaction monitoring | Compliance | **Unconfirmed — no dedicated AML/CFT policy document exists yet**, see [`37-kyc-aml-policy.md`](37-kyc-aml-policy.md) |
| Suspicious Transaction Reports within 7 days | FMU (Financial Monitoring Unit) | Transaction monitoring | Compliance | **Unconfirmed — no STR filing process referenced in engineering docs** |
| Automatic Currency Transaction Report detection | FMU | Transaction monitoring | Compliance | **Unconfirmed — no CTR detection logic referenced in engineering docs** |
| CNIC identity verification | NADRA | KYC pipeline | Engineering (Gateway) | **Integration is a stub in current code** — see [`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md) |
| Mandatory credit bureau reporting | TASDEEQ | Loan performance reporting | Ledger Service | Partially designed (positive/negative reporting triggers referenced in the collections timeline); **not confirmed as a live, working integration** |
| Data residency (Pakistan) | PECA 2016 | Infrastructure | Engineering/Infra | AWS `ap-south-1` chosen specifically for this — see [`../10-devops/33-infrastructure-architecture.md`](../10-devops/33-infrastructure-architecture.md) |
| OTP-based e-signatures | PECA 2016 / Electronic Transactions Ordinance 2002 §15 | Contract signing (Wakalah, Murabaha) | Engineering (Gateway) | Implemented as designed — OTP + confirmation checkbox on Murabaha signing |
| Shariah Board quarterly audit + annual contract certification | Internal Shariah governance (referencing SECP's Shariah governance framework) | Contract templates | Shariah Board | **Not yet operational** — see [`../04-shariah/18-shariah-governance.md`](../04-shariah/18-shariah-governance.md), [`19-shariah-review-register.md`](../04-shariah/19-shariah-review-register.md) |
| NADRA raw response retention (7 years) | Cited as a SECP requirement | KYC data retention | Engineering/Compliance | Implemented in schema (`nadra_raw_response` JSONB) — **retention-period citation itself not independently verified** |

## What this document is not

- Not a substitute for a formal regulatory gap analysis performed by counsel.
- Not confirmation that SahulatKar is currently operating in compliance with any of the above.
- Not a complete list — e.g., consumer-protection-specific obligations (fair treatment, complaints handling) are covered separately in [`38-responsible-financing-policy.md`](38-responsible-financing-policy.md) and reference SECP's broader digital-lending disclosure framework (Borrower Factsheet requirements, etc.) without this document independently verifying current applicability.

## Immediate recommended actions for Legal/Compliance

1. Confirm SahulatKar's actual current licensing/registration status with SECP and record it authoritatively (this repository currently has no record of it at all).
2. Independently verify every regulator citation in the table above against current, dated regulatory text — several (SECP NBFC Circular 15/2022, the 7-year NADRA retention requirement) appear to be cited from secondary/engineering sources rather than the primary regulatory text.
3. Decide who owns each row — the "Owner (proposed)" column is engineering's best guess at a sensible RACI, not an assigned responsibility.
4. Prioritize closing the AML/CFT and STR/CTR gaps specifically — these have no implementation referenced anywhere in the codebase, unlike KYC (stubbed but at least designed) or data residency (actually implemented).

## Related documents

[`37-kyc-aml-policy.md`](37-kyc-aml-policy.md), [`38-responsible-financing-policy.md`](38-responsible-financing-policy.md), [`../04-shariah/17-shariah-product-structure.md`](../04-shariah/17-shariah-product-structure.md).
