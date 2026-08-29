# Merchant Risk Policy

**Status:** STABLE (mechanism exists) — formal policy does not.

## What functions as merchant risk management today

`merchants.bot_detection_level`, `checkout_success_rate`, and `status` (`active`/`degraded`/`blocked`/`monitoring`) — see [`../17-merchant-documentation/66-merchant-lifecycle.md`](../17-merchant-documentation/66-merchant-lifecycle.md). This is **operational reliability risk** (can we successfully transact against this domain), not counterparty/credit risk (is this a legitimate, trustworthy business) — SahulatKar has no mechanism assessing the latter at all, since it has no ongoing exposure to a merchant the way a settlement relationship would create.

## What a merchant risk policy would need to add, if this becomes a real gap

If the platform ever needs to assess whether a specific site is likely fraudulent (selling counterfeit goods, non-delivering, a scam storefront) — as distinct from whether the checkout automation *works* against it — no policy or mechanism currently exists for this. This is worth Product/Risk considering explicitly: a customer who financed a purchase from a fraudulent site still owes SahulatKar the full Murabaha repayment even if the "product" was fake or never arrived, which is a real risk exposure the current design doesn't appear to address at the point of purchase (only after the fact, via delivery-exception handling).

## Related documents

[`../17-merchant-documentation/66-merchant-lifecycle.md`](../17-merchant-documentation/66-merchant-lifecycle.md), [`../12-operations/40-merchant-vendor-support-sop.md`](../12-operations/40-merchant-vendor-support-sop.md).
