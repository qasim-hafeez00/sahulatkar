# Merchant Suspension Policy

**Status:** STABLE — the closest equivalent is `merchants.status = 'blocked'`, an internal operational flag, not a suspension in any relationship sense (there's no account to suspend).

## What determines a domain being marked `blocked`

Not formally specified — presumably a combination of persistent extraction/checkout failure and/or a high observed rate of the merchant's own systems rejecting SahulatKar's purchasing pattern (see [`../18-credit-risk-policy/93-fraud-risk-framework.md`](../18-credit-risk-policy/93-fraud-risk-framework.md)'s "merchant-side fraud" gap — the platform currently has no formal detection for this, so `blocked` status likely results from manual observation rather than an automated threshold today).

## Consequence of `blocked` status

The checkout agent will not attempt purchases against a `blocked` domain — customers pasting a URL from such a domain would presumably still get extraction results (if extraction itself still works) but fail at the offer/checkout stage. Not confirmed exactly how this surfaces to the customer — recommend Product confirm the UX for this specific case.

## Un-blocking

No documented process — presumably a manual engineering/ops decision to revert `status` once whatever caused the block is resolved (e.g., a `scrape_config` fix, or the merchant's own block lapsing). No formal review cadence exists for re-testing blocked domains periodically.

## Related documents

[`../17-merchant-documentation/66-merchant-lifecycle.md`](../17-merchant-documentation/66-merchant-lifecycle.md), [`194-merchant-risk-policy.md`](194-merchant-risk-policy.md).
