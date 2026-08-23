# Transaction Monitoring

> **STATUS: INTERNAL DRAFT.** Names a gap rather than describing a working system — no dedicated transaction-monitoring capability exists in current engineering documentation, distinct from (though overlapping with) the Credit Engine's velocity/fraud rules.

## Why credit-engine velocity rules are not the same thing as AML transaction monitoring

The Credit Engine's Layer 2 velocity rules (see [`../18-credit-risk-policy/94-fraud-detection-rules.md`](../18-credit-risk-policy/94-fraud-detection-rules.md)) monitor for **credit-risk and first-party-fraud patterns** — too many orders, too many failed payments, too many new accounts from one IP. AML transaction monitoring typically looks for a different pattern set: structuring (breaking a transaction into smaller pieces to avoid a reporting threshold), unusual velocity relative to a customer's established profile, transactions inconsistent with stated purpose, and patterns associated with money laundering typologies specifically — not credit risk. These are related but genuinely distinct monitoring objectives, and the existing velocity rules were not designed with the AML objective in mind.

## What's referenced but not built

FMU's Suspicious Transaction Report (7-day filing window) and automatic Currency Transaction Report detection are cited in [`36-compliance-requirements-matrix.md`](36-compliance-requirements-matrix.md) as applicable obligations — but no transaction-monitoring logic, threshold configuration, or alert-generation mechanism aimed at *these specific* typologies exists anywhere in the reviewed codebase.

## Recommended approach

Rather than building a wholly separate transaction-monitoring system, Compliance and Engineering should assess whether the existing `fraud_rules` configurable-rule infrastructure (JSONB condition-based rules, already built for credit-risk purposes — see [`../18-credit-risk-policy/94-fraud-detection-rules.md`](../18-credit-risk-policy/94-fraud-detection-rules.md)) can be extended with a distinct AML-focused rule set, reusing the mechanism while keeping the rule *content* clearly separated and owned by Compliance rather than Risk.

## Related documents

[`37-kyc-aml-policy.md`](37-kyc-aml-policy.md), [`../18-credit-risk-policy/94-fraud-detection-rules.md`](../18-credit-risk-policy/94-fraud-detection-rules.md), [`36-compliance-requirements-matrix.md`](36-compliance-requirements-matrix.md).
