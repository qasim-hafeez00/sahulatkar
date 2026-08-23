# KYC / AML Policy

> **STATUS: INTERNAL DRAFT.** This document describes the KYC *mechanism as designed and partially implemented* (see [`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md) for the full technical workflow) plus the AML obligations *referenced* in engineering documentation. It is not a board-approved AML policy and has not been reviewed by compliance counsel. **A dedicated, formal AML/CFT program document does not exist anywhere in this repository as of this writing** — this document identifies that as a gap rather than papering over it with invented policy.

## KYC — what exists

Full technical detail: [`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md). Summary for compliance purposes: CNIC OCR + NADRA Verisys check + liveness/face-match, two-tier structure (Tier 1 standard, Tier 2 EDD for orders >PKR 5,000 or a fraud flag), manual review for borderline results, 7-year retention of raw NADRA responses (citation not independently verified), rejection with a 30-day re-application cooldown.

**Material caveat for compliance purposes:** NADRA and the liveness/OCR vendor (Shufti Pro) integrations are **stubs in the current codebase — no real third-party verification call is made.** Any compliance sign-off on "SahulatKar performs NADRA-verified KYC" should be understood as describing the *design*, not the *current operational reality*, until this is confirmed fixed.

## AML — what is referenced but not built

Engineering documentation references SBP AML/CFT obligations and FMU reporting (Suspicious Transaction Reports within 7 days, automatic Currency Transaction Report detection) in a single summary table (see [`36-compliance-requirements-matrix.md`](36-compliance-requirements-matrix.md)) — but **no AML transaction-monitoring logic, no STR filing workflow, and no CTR detection logic appears anywhere in the codebase or module specs reviewed for this knowledge base.** This is the single largest compliance gap identified in this documentation pass: the platform has designed and partially built identity verification (KYC) but has essentially no documented or implemented transaction-monitoring/AML program.

## Sanctions / watchlist screening

Referenced once, as a manual-review trigger: "High-risk sanctions watchlist — any match" routes to manual KYC review (see [`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md)). No detail exists on which watchlist(s) are screened against, how often the list is refreshed, or whether this is automated or a manual check — **this needs Compliance to specify.**

## Fraud/velocity controls (adjacent to, but distinct from, AML)

The Credit Engine's Layer 1 (hard blocks) and Layer 2 (velocity rules) — see [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md) — provide fraud and abuse-pattern detection (blacklist checks, order/KYC/promo velocity limits) that overlaps functionally with what an AML transaction-monitoring program would need, but is explicitly designed and described as a *credit-risk/fraud* control, not an AML control. Compliance should assess whether these existing signals can be extended/repurposed for STR-triggering purposes, or whether a separate AML monitoring layer is required.

## Recommended actions for Compliance/Legal

1. **Commission a formal AML/CFT program document** — this gap is more urgent than most others in this knowledge base, since it currently has zero documented design, not just an implementation gap against a design (unlike KYC, which at least has a fully speced pipeline).
2. Confirm the sanctions-watchlist screening mechanism and document it explicitly.
3. Define the STR/CTR filing process and who at the company is the accountable Money Laundering Reporting Officer (MLRO) or equivalent — no such role is referenced anywhere in current documentation.
4. Once NADRA/Shufti Pro integrations are confirmed live in code, re-verify this document's KYC section against actual behavior rather than design intent.

## Related documents

[`36-compliance-requirements-matrix.md`](36-compliance-requirements-matrix.md), [`38-responsible-financing-policy.md`](38-responsible-financing-policy.md), [`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md).
