# Merchant KPIs

**Status:** STABLE — deliberately thin, since "merchant" in this platform means "tracked third-party domain," not an onboarded partner (see [`../17-merchant-documentation/65-merchant-overview.md`](../17-merchant-documentation/65-merchant-overview.md)). These KPIs are internal operational metrics, not partner-performance metrics.

## KPIs

| KPI | Definition | Source |
|---|---|---|
| Checkout success rate (per domain) | % of checkout attempts against a given domain that complete successfully | `merchants.checkout_success_rate`, `mv_merchant_performance` |
| Extraction success rate (per domain) | % of URL submissions from a domain that successfully produce a UPO | `scraping_jobs` aggregated by `merchant_id` |
| Merchant-ban rate (per domain) | % of purchasing attempts against a domain that get blocked/reversed by the merchant's own fraud detection — **not currently tracked**, a recommended addition (see [`../12-operations/40-merchant-vendor-support-sop.md`](../12-operations/40-merchant-vendor-support-sop.md)) |
| Top-domain GMV concentration | % of total GMV flowing through the top N domains — a diversity/concentration health check, relevant given Layer 7's 20%-per-merchant portfolio concentration limit (see [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md)) |

## Why there's no "merchant satisfaction" or "merchant retention" KPI

These would be standard in a merchant-network BNPL's KPI set — they don't apply here because merchants have no relationship to be satisfied with or retained in. The closest equivalent concern (does the platform continue to be able to transact against a given domain reliably) is captured by checkout/extraction success rate instead.

## Related documents

[`../17-merchant-documentation/66-merchant-lifecycle.md`](../17-merchant-documentation/66-merchant-lifecycle.md), [`../12-operations/40-merchant-vendor-support-sop.md`](../12-operations/40-merchant-vendor-support-sop.md).
