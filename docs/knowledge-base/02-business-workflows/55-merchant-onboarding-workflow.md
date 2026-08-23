# Merchant Onboarding Workflow

**Status:** STABLE — **this workflow does not exist**, and this document explains why deliberately rather than leaving the slot silently empty. See [`06-merchant-vendor-journey.md`](06-merchant-vendor-journey.md) for the full explanation of the vendor-agnostic model this stems from.

## Why there is no onboarding workflow

SahulatKar does not onboard merchants. Every third-party website is transactable the moment a customer pastes a URL pointing to it — there is no application, no approval step, no KYB check, no integration to complete. This is a deliberate architectural choice (universal coverage, see [`../01-company-product/01-product-overview.md`](../01-company-product/01-product-overview.md)), not a missing feature.

## What happens instead, operationally

1. A customer pastes a URL from a site SahulatKar has never seen before.
2. The extraction waterfall attempts to parse it (Rye API → JSON-LD → Playwright+LLM → HITL) with no site-specific setup required.
3. If extraction succeeds, a `merchants` row is created/updated automatically with the domain, detected platform type, and default extraction settings — this is **data capture, not onboarding**, since it requires no action or awareness from the site.
4. If a specific site proves consistently difficult (CAPTCHA-heavy, bot-detection blocks, broken generic extraction), Engineering may add a site-specific `scrape_config` override — this is the closest thing to a "manual onboarding" step that exists, and it's an internal engineering task, not a merchant-facing process.

## The one exception: "affiliate partner" tier

A small subset of merchants — Shopify/Amazon-class stores reachable via the Rye extraction API — are tracked with `is_affiliate_partner = true` and a `commission_rate`. Whether this represents an actual onboarding relationship with those specific merchants, or is simply inherited from Rye's own merchant network (i.e., no direct SahulatKar-merchant relationship at all), is **not clarified in current engineering documentation** — flagged in [`06-merchant-vendor-journey.md`](06-merchant-vendor-journey.md) as something Business Development should confirm.

## If this changes

If SahulatKar later decides to build real merchant partnerships (see the "If SahulatKar later adds real merchant partnerships" note in [`06-merchant-vendor-journey.md`](06-merchant-vendor-journey.md)), this document is the one to replace with an actual onboarding workflow — trigger, application, KYB verification, integration/API agreement, go-live — none of which should be adapted from this document, since the trust and liability model would be fundamentally different.

## Related documents

[`06-merchant-vendor-journey.md`](06-merchant-vendor-journey.md), [`../17-merchant-documentation/67-merchant-onboarding-requirements.md`](../17-merchant-documentation/67-merchant-onboarding-requirements.md).
