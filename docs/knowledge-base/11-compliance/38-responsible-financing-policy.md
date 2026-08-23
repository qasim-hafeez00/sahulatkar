# Responsible Financing Policy

> **STATUS: INTERNAL DRAFT.** Like [`37-kyc-aml-policy.md`](37-kyc-aml-policy.md), this document identifies what currently exists in engineering design that's *relevant* to responsible-financing/consumer-protection obligations, and explicitly flags what does not yet exist as policy. Not reviewed by compliance counsel. Not a substitute for a formal responsible-lending policy signed off by Risk, Compliance, and Legal.

## What exists today that supports responsible financing

- **Affordability-adjacent underwriting parameters:** max debt-to-income ratio (default 40%, configurable range 30–50%) and minimum monthly income requirement (default PKR 30,000, range PKR 20K–50K) are defined as credit-policy parameters — see [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md). **Caveat:** these live in a `system_parameters` table with no working admin CRUD API yet (`GW-GAP-01`), so they are effectively hardcoded defaults today, not actively managed policy levers.
- **Cold-start exposure caps:** first-time users are capped well below their nominal credit-band limit (e.g., a Band A user's first order is capped at PKR 8,000 against a PKR 25,000 band limit) — a deliberate design choice to limit exposure before a repayment track record exists. See [`../03-bnpl-financing/15-credit-limit-rules.md`](../03-bnpl-financing/15-credit-limit-rules.md).
- **Full upfront cost disclosure:** enforced at the database level, not just in the UI — a Murabaha contract cannot be generated without `cost_price`, `profit_amount`, and `total_repayable` all populated. This directly supports a "customer sees the true total cost before committing" principle.
- **No compounding, no hidden fees:** the only cost is the disclosed markup baked into the fixed installment schedule at signing; late fees are not a platform-revenue lever (100% charity-routed), which structurally removes an incentive some might worry the platform could otherwise have to encourage or profit from customer default.
- **SECP-citation-linked explainability:** declined/borderline credit decisions are designed to generate a SHAP explanation with human-readable factors — see [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md). Whether this satisfies an actual SECP borrower-disclosure requirement (e.g., a "Borrower Factsheet"-style simplified disclosure, referenced in general BNPL regulatory research but not confirmed against SahulatKar's specific obligations) is a legal question, not an engineering one.

## What does not yet exist — genuine gaps for Compliance/Product to close

- **No portfolio-level default-rate target or loss-provisioning policy.** The only documented default-related figure in engineering docs is a single-order break-even default rate (~1.9%, see [`../01-company-product/03-business-model.md`](../01-company-product/03-business-model.md)) — not a responsible-lending target or a provisioning policy.
- **No documented complaints/grievance procedure.** Nothing in current engineering docs describes how a customer complaint is logged, escalated, or resolved with an SLA — see the equivalent gap noted in [`../12-operations/39-customer-support-sop.md`](../12-operations/39-customer-support-sop.md).
- **No formal hardship/restructuring policy.** A payment-restructuring admin capability is speced (AD-08) but not implemented (`GW-GAP-05`) — meaning there is currently no mechanism, policy or technical, for a customer facing genuine hardship to get a modified repayment plan rather than proceeding straight down the standard collections-escalation timeline (see [`../02-business-workflows/10-default-collections-workflow.md`](../02-business-workflows/10-default-collections-workflow.md)).
- **No documented late-fee cap policy verification.** Shariah principle holds that a late fee should not exceed the underlying principal — current code does not verify this bound is respected (`LS-BL-08`, also noted in [`../02-business-workflows/10-default-collections-workflow.md`](../02-business-workflows/10-default-collections-workflow.md)).
- **No standalone minimum/maximum order-size policy** beyond what credit limits happen to allow — see the corresponding note in [`../03-bnpl-financing/13-payment-plan-rules.md`](../03-bnpl-financing/13-payment-plan-rules.md).

## Recommended actions for Compliance/Risk/Product

1. Formalize a written responsible-financing policy covering affordability assessment, hardship/restructuring options, and a complaints procedure — none currently exists as a standalone document.
2. Confirm whether SECP's digital-lending disclosure framework (simplified borrower disclosures, fair-treatment requirements) applies to SahulatKar's specific licensing category, and if so, map each requirement to a concrete product/UX commitment.
3. Prioritize implementing the payment-restructuring capability (`GW-GAP-05`) — it's currently the single missing piece standing between "no hardship option exists" and "a documented, product-supported hardship path exists."

## Related documents

[`36-compliance-requirements-matrix.md`](36-compliance-requirements-matrix.md), [`37-kyc-aml-policy.md`](37-kyc-aml-policy.md), [`../02-business-workflows/10-default-collections-workflow.md`](../02-business-workflows/10-default-collections-workflow.md).
