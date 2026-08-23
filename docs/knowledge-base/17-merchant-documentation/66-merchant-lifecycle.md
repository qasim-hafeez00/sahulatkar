# Merchant Lifecycle

**Status:** STABLE — describes the lifecycle of a `merchants` table row (a tracked domain), since that's the only thing resembling a "merchant lifecycle" that exists in this platform.

## Lifecycle of a tracked domain

```
Unknown (a URL from this domain has never been submitted)
  ↓
First encountered (a customer pastes a URL; extraction attempted)
  ↓
Tracked (a `merchants` row exists: domain, platform_type, scrape_config defaults)
  ↓
Active | Degraded | Blocked | Monitoring   (per `merchants.status`)
```

This is **not** a lifecycle the domain/business opts into, agrees to, or is even aware of — it's purely internal operational metadata SahulatKar maintains to route and tune its own extraction/checkout automation. Compare to [`62-customer-lifecycle.md`](../16-customer-documentation/62-customer-lifecycle.md) for the customer-side equivalent, which *is* a genuine onboarded-party lifecycle — the contrast is the point of this document.

## Status meanings (`merchants.status`)

| Status | Meaning |
|---|---|
| `active` | Extraction/checkout has recently succeeded against this domain |
| `degraded` | Extraction/checkout is failing intermittently — may need a `scrape_config` update |
| `blocked` | The domain consistently blocks SahulatKar's automation (bot detection, account/card bans) — see [`../12-operations/40-merchant-vendor-support-sop.md`](../12-operations/40-merchant-vendor-support-sop.md) |
| `monitoring` | Recently added or recently changed behavior, under closer observation |

## What ends a domain's "lifecycle"

There's no formal offboarding — a domain simply stops being purchasable if it's marked `blocked` (checkout automation won't attempt it) or if extraction consistently fails and nobody prioritizes fixing it. There's no customer-facing notice that a specific site has become unsupported beyond the extraction failing at the point of URL submission.

## Related documents

[`65-merchant-overview.md`](65-merchant-overview.md), [`../02-business-workflows/06-merchant-vendor-journey.md`](../02-business-workflows/06-merchant-vendor-journey.md), [`../07-database/26-database-dictionary.md`](../07-database/26-database-dictionary.md) (`merchants` table).
