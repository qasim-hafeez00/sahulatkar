# Merchant Verification / KYB

**Status:** STABLE — not applicable. Confirmed here explicitly since KYB is a standard fintech documentation category and its absence should be a documented decision, not a silent gap.

## Why there is no KYB

Know-Your-Business verification exists to establish a *regulated relationship* with a business counterparty (typically required when a platform is settling funds to that business, extending it credit, or otherwise creating financial exposure to it). SahulatKar has none of these relationships with the sites it purchases from — it pays them in full, immediately, exactly as any individual consumer's own card would. There is no settlement, no credit extension, and no ongoing financial relationship to a merchant that would require verifying who they are.

## What partially resembles KYB, and why it isn't

The `merchants` table tracks `domain`, `platform_type`, `checkout_success_rate`, and `bot_detection_level` — this is **extraction/checkout reliability metadata**, not identity or business verification. No effort is made to confirm a domain is operated by a legitimate registered business, is not itself fraudulent, or meets any regulatory standard — SahulatKar's exposure to a fraudulent or fly-by-night site is the same as any individual online shopper's (non-delivery risk, quality risk), not a platform-level counterparty risk requiring formal verification.

## If this changes

If a future "affiliate partner" tier evolves into genuine merchant partnerships with revenue-sharing or settlement obligations (see [`75-merchant-commission-fee-model.md`](75-merchant-commission-fee-model.md)), KYB would become a real requirement for that specific tier — this document should be revisited at that point, not extended to retroactively imply it applies today.

## Related documents

[`65-merchant-overview.md`](65-merchant-overview.md), [`../01-company-product/04-product-glossary.md`](../01-company-product/04-product-glossary.md) (KYB glossary entry).
