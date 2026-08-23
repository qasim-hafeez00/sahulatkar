# Merchant / Vendor Support SOP

**Status:** STABLE — scoped deliberately narrowly, because (as explained in [`../02-business-workflows/06-merchant-vendor-journey.md`](../02-business-workflows/06-merchant-vendor-journey.md)) there is no merchant account, portal, or support channel in this product. This SOP covers **internal handling of merchant-side friction**, not merchant-facing customer support.

## Scope

This SOP applies when the checkout agent or extraction pipeline hits friction caused by a specific third-party site: an account/card block, a CAPTCHA wall, a broken extraction, or a refused return — situations where "the merchant" is effectively an obstacle to route around, not a party to communicate with as a partner.

## Trigger scenarios

| Scenario | Detected by | First response |
|---|---|---|
| Checkout blocked (bot detection, CAPTCHA unsolvable, VCN declined by merchant) | Checkout agent failure → HITL queue | Ops/HITL operator attempts manual completion or escalates per [`39-customer-support-sop.md`](39-customer-support-sop.md) |
| Extraction consistently failing for a specific domain | Repeated `scraping_jobs` failures against the same `merchant_id` | Engineering investigates `scrape_config` (per-merchant CSS/XPath overrides); update or add merchant-specific extraction rules |
| VCN/card pattern appears blocked platform-wide by a merchant | No current automated detection — **known gap**, see below | Manual observation by Ops today; should become a monitored metric |
| Merchant refuses a return/warranty claim | Customer support escalation | **No documented resolution process exists** — this is a genuine open policy question flagged in [`../02-business-workflows/06-merchant-vendor-journey.md`](../02-business-workflows/06-merchant-vendor-journey.md), not just an SOP gap |

## Known gap: no merchant-ban-rate monitoring

Unlike `checkout_success_rate` (tracked per merchant in the `merchants` table and feeding into routing/reliability decisions), there is currently no documented or implemented metric for "how often does this merchant's own fraud/bot-detection system block our purchasing pattern" — this is a real operational risk specific to the vendor-agnostic model (see the general BNPL research in `docs/Sahulatkar-docs/` on merchant account-ban risk) that current engineering docs don't yet track as a first-class signal. Recommend adding this to the merchant metadata model and to [`../13-analytics/42-kpi-metrics-dictionary.md`](../13-analytics/42-kpi-metrics-dictionary.md).

## Escalation path

1. **Engineering/Product Service on-call** — extraction or checkout-automation breakage against a specific site.
2. **Operations (HITL team)** — individual order stuck due to merchant-side friction.
3. **Business Development** *(if this role exists — not confirmed in current org documentation)* — for the small "affiliate partner" tier (Rye-API-integrated Shopify/Amazon-class stores), where an actual relationship might exist to escalate through, as opposed to the general case of an arbitrary unaffiliated site.
4. **Legal** — for the returns/dispute-refusal open policy question, since resolving it (who absorbs cost, what disclosure customers get) is a legal/product decision, not something Ops can resolve ad hoc per incident.

## Related documents

[`../02-business-workflows/06-merchant-vendor-journey.md`](../02-business-workflows/06-merchant-vendor-journey.md), [`39-customer-support-sop.md`](39-customer-support-sop.md), [`../05-architecture/microservices/product-service.md`](../05-architecture/microservices/product-service.md).
