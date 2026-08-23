# Merchant / Vendor Journey

**Status:** STABLE — this document deliberately does not follow a standard BNPL "merchant onboarding" template, because SahulatKar has no such pipeline. Read this before any other merchant-related document in this knowledge base.

## Why this document looks different from a typical BNPL merchant-journey doc

Most BNPL platforms (Klarna, Affirm, Tabby) require a merchant to sign up, integrate a checkout SDK/API, and agree to a settlement/fee arrangement — the merchant is a first-class, onboarded party. **SahulatKar has none of this.** Its checkout agent purchases from any website exactly as an ordinary retail customer would, using a single-use virtual card. The "merchant" is whichever store the customer's pasted URL happens to point to, whether that's Amazon, a Shopify store, Daraz, or a small independent retailer with no awareness that a BNPL platform is involved.

This is a deliberate product choice (universal coverage without merchant integration — see [`../01-company-product/01-product-overview.md`](../01-company-product/01-product-overview.md)) with real operational consequences, which this document covers.

## What "merchant" means in the data model

The `merchants` table (see [`../07-database/26-database-dictionary.md`](../07-database/26-database-dictionary.md)) tracks: `name`, `domain`, `platform_type`, `checkout_success_rate`, `has_captcha`/`bot_detection_level`, `scrape_config` (per-merchant CSS/XPath overrides for extraction), and an `is_affiliate_partner` flag with `commission_rate` for a small tracked subset. None of these fields imply the merchant opted in — they're operational metadata SahulatKar maintains internally to route and tune its own checkout automation.

## "Affiliate partner" tier

A subset of merchants — currently the Shopify/Amazon-class stores reachable through the Rye extraction API (Tier 1 of the extraction waterfall) — are tracked with a `commission_rate`. Whether this represents an actual commercial agreement or just an API-provider relationship (i.e., Rye's own merchant network, not a direct SahulatKar-merchant relationship) is not clarified in current engineering documentation — **flag for Business Development to confirm** before this is described externally as a "partnership."

## Operational implications of the vendor-agnostic model

Documented as top business/technical risks in the platform's own research (`docs/Sahulatkar-docs/` and `Desktop/bnpl/general/`), and directly relevant to how this platform must be operated day to day:

| Risk | Why it exists in this model specifically | Where it's handled |
|---|---|---|
| **Merchant account bans** | Repeated purchases from the same VCN issuer / IP pattern can look like fraud to the merchant's own systems and get the purchasing "account" or card blocked. | Mitigated by residential proxy rotation (BrightData), VCN single-use design, and stealth browser automation — see [`../05-architecture/microservices/product-service.md`](../05-architecture/microservices/product-service.md). No documented merchant-ban-rate monitoring exists yet in the codebase — a gap worth closing before scale. |
| **Returns & disputes** | SahulatKar is not the merchant's "customer of record" in any contractual sense — merchants may refuse to process a return or warranty claim initiated by SahulatKar rather than the named cardholder. | Not resolved in current engineering docs. The refund pathway itself is unimplemented in code (`RefundOrchestrator` is a stub) regardless of the merchant-return question — see [`09-refund-cancellation-workflow.md`](09-refund-cancellation-workflow.md). This is a genuine open design question for Product/Legal, not just an engineering gap. |
| **Price/availability drift** | The product's price or stock status can change between extraction and actual checkout (minutes to hours later). | Price-staleness worker exists (`price_staleness_worker.py`) but a >5% price-change re-confirmation flow is not fully wired per the last audit (PS-BL-11 / related gaps). |
| **Checkout automation reliability** | Every merchant website is a different, unmaintained integration target — no API contract, just whatever HTML/JS the site happens to render. | Extraction waterfall + self-healing VLM agent + HITL fallback — see [`07-bnpl-workflow-e2e.md`](07-bnpl-workflow-e2e.md) step 10. |

## Merchant support

Because there is no merchant portal, account, or support channel, [`../12-operations/40-merchant-vendor-support-sop.md`](../12-operations/40-merchant-vendor-support-sop.md) is scoped narrowly: it covers internal handling of merchant-side friction (bans, blocked checkouts, broken extraction) as an **operations/engineering problem**, not merchant-facing customer support in the traditional sense.

## Settlement

See [`11-merchant-settlement-reconciliation.md`](11-merchant-settlement-reconciliation.md) — there is no merchant settlement (SahulatKar pays merchants in full at checkout, same as any retail customer); what's reconciled is SahulatKar's own payment-gateway collections.

## If SahulatKar later adds real merchant partnerships

If a future product decision introduces true merchant onboarding (API checkout integration, negotiated commission, merchant dashboard), this document — and the KYB placeholder in [`../01-company-product/04-product-glossary.md`](../01-company-product/04-product-glossary.md) — should be rewritten from scratch against the new design rather than patched, since the trust/liability/settlement model would be fundamentally different from what's described here.
