# Merchant Overview

**Status:** STABLE — read [`../02-business-workflows/06-merchant-vendor-journey.md`](../02-business-workflows/06-merchant-vendor-journey.md) first; this document is the "Merchant Documentation" category's entry point and summarizes why every document in this folder looks unlike a typical BNPL merchant-documentation set.

## The one-sentence summary

SahulatKar has no merchants, in the sense that term is normally used in BNPL — it has **arbitrary third-party websites it purchases from**, with no account, agreement, or integration on their side.

## What this folder covers instead

Since a standard "merchant documentation" set (overview, lifecycle, onboarding, KYB, dashboard, checkout/order/settlement/refund/dispute flows, commission model, integration guide) assumes an onboarded partner, each document in this folder either:

1. **Explains what actually happens instead** for that topic, given the vendor-agnostic model, or
2. **Describes the target design** for the small "affiliate partner" tier, where something closer to a traditional merchant relationship *might* exist, flagged as unconfirmed pending Business Development input, or
3. **Explicitly states the topic doesn't apply**, with a pointer to what governs the equivalent concern in this platform.

## Index of this folder

| Document | What it actually covers |
|---|---|
| [`66-merchant-lifecycle.md`](66-merchant-lifecycle.md) | The lifecycle of a *tracked domain* in the `merchants` table — not an onboarded partner |
| [`67-merchant-onboarding-requirements.md`](67-merchant-onboarding-requirements.md) | Why there are no requirements to onboard, and what minimal criteria make a site "supported" |
| [`68-merchant-verification-kyb.md`](68-merchant-verification-kyb.md) | Confirms KYB is not applicable |
| [`69-merchant-dashboard-requirements.md`](69-merchant-dashboard-requirements.md) | Confirms no merchant-facing dashboard exists or is planned |
| [`70-merchant-checkout-flow.md`](70-merchant-checkout-flow.md) | The checkout agent's interaction with a merchant site, from the merchant's-eye view |
| [`71-merchant-order-flow.md`](71-merchant-order-flow.md) | How an order appears (or doesn't) from the merchant's systems' perspective |
| [`72-merchant-settlement-flow.md`](72-merchant-settlement-flow.md) | Confirms there is no settlement — payment is immediate, at checkout |
| [`73-merchant-refund-flow.md`](73-merchant-refund-flow.md) | The open policy question around merchant-side returns |
| [`74-merchant-dispute-flow.md`](74-merchant-dispute-flow.md) | What happens when a merchant disputes/blocks a transaction |
| [`75-merchant-commission-fee-model.md`](75-merchant-commission-fee-model.md) | The one place a commission concept exists (affiliate tier) and its unconfirmed status |
| [`76-merchant-integration-guide.md`](76-merchant-integration-guide.md) | Confirms there is no integration to build, for any merchant who asks |

## Related documents

[`../02-business-workflows/06-merchant-vendor-journey.md`](../02-business-workflows/06-merchant-vendor-journey.md) (the canonical explanation this whole folder is built on), [`../21-business-merchant-operations/`](../21-business-merchant-operations/) (the business-side equivalent of this gap).
