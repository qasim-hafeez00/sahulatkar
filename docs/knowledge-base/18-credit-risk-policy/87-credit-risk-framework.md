# Credit Risk Framework

**Status:** STABLE — the policy-level framing of the Credit Engine's mechanics, which are fully specified in [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md). This document is the "why/how do we think about risk" companion to that "what exactly runs" document.

## Framework structure

Risk is managed at three levels, each with its own controls:

1. **Transaction-level (per order):** the 7-layer real-time pipeline — hard blocks, velocity, identity/device, alternative data, ML scoring, category overlay. See [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md).
2. **Customer-level (across orders):** credit band, limit, and cold-start caps that constrain a single customer's total exposure over time. See [`../03-bnpl-financing/15-credit-limit-rules.md`](../03-bnpl-financing/15-credit-limit-rules.md).
3. **Portfolio-level (across all customers):** concentration limits (Layer 7) capping exposure by product category, city, merchant, and cold-start-user proportion — the platform's defense against correlated risk (e.g., a single category or fraud ring taking down a disproportionate share of the book).

## Why thin-file underwriting is the framework's central design problem

Most of the platform's risk architecture exists to solve one specific problem: **most applicants have no traditional credit bureau history.** This is why alternative data (device signals, KYC verification quality, telco data) and cold-start caps (aggressive first-order limits regardless of nominal band) exist — they're both direct responses to not being able to lean on bureau history the way a conventional lender would.

## Risk appetite (the only hard figure documented)

The single quantified risk-appetite figure in engineering docs is the break-even default rate on a reference order (~1.9%, see [`../01-company-product/03-business-model.md`](../01-company-product/03-business-model.md)). No broader portfolio-level default rate target, loss-provisioning policy, or risk-appetite statement exists — this is the most significant gap in the framework as documented, flagged also in [`../11-compliance/38-responsible-financing-policy.md`](../11-compliance/38-responsible-financing-policy.md). **Recommend Risk leadership define an explicit risk appetite statement** (target default rate, acceptable loss ratio, capital-at-risk limits) that the credit-band structure and portfolio concentration limits can then be validated against.

## Related documents

[`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md), [`../03-bnpl-financing/15-credit-limit-rules.md`](../03-bnpl-financing/15-credit-limit-rules.md), [`97-credit-policy.md`](97-credit-policy.md), [`92-risk-segmentation.md`](92-risk-segmentation.md).
