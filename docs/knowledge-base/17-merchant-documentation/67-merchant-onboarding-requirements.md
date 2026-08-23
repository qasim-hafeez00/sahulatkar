# Merchant Onboarding Requirements

**Status:** STABLE — there are none. See [`../02-business-workflows/55-merchant-onboarding-workflow.md`](../02-business-workflows/55-merchant-onboarding-workflow.md) for the full explanation.

## What would normally be required, and why none of it applies here

| Typical BNPL requirement | Status in SahulatKar |
|---|---|
| Business registration/legitimacy check | Not required — SahulatKar transacts as a retail customer, the same check any consumer's own card issuer would (or wouldn't) apply |
| Checkout SDK/API integration | Not required — the checkout agent uses the site's normal consumer-facing checkout flow, not an API |
| Settlement/fee agreement | Not required — see [`72-merchant-settlement-flow.md`](72-merchant-settlement-flow.md) |
| Terms of service acceptance | Not required, and not obtained — SahulatKar's terms with the *customer* govern the transaction; whether the *merchant's own* consumer ToS technically prohibits automated/third-party purchasing is a live legal question referenced in the general BNPL research (`docs/Sahulatkar-docs/`) but not resolved in this codebase |

## The closest thing to a "requirement": extraction compatibility

The only practical gate a site faces is whether SahulatKar's extraction waterfall can successfully parse it (Rye API, JSON-LD, or Playwright+LLM) and whether its checkout flow is automatable. This is a technical capability question, not an onboarding requirement — a site doesn't need to do anything to become "supported"; it either works with the extraction/checkout pipeline or it doesn't, and if it doesn't, Engineering may invest in a site-specific fix (see [`../12-operations/40-merchant-vendor-support-sop.md`](../12-operations/40-merchant-vendor-support-sop.md)).

## Related documents

[`65-merchant-overview.md`](65-merchant-overview.md), [`../02-business-workflows/55-merchant-onboarding-workflow.md`](../02-business-workflows/55-merchant-onboarding-workflow.md).
