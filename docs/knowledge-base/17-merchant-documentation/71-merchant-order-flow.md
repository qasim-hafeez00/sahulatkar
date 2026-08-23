# Merchant Order Flow (from the merchant's systems' perspective)

**Status:** STABLE

## What the merchant's own order-management system records

Exactly what it would for any ordinary customer order: an order ID, a shipping address (SahulatKar's customer's address, entered by the checkout agent), a payment method (the single-use VCN, which appears to the merchant as a normal card), and a fulfillment/shipping obligation. The merchant's systems have no field, flag, or signal indicating this order originated from a BNPL platform's automated agent rather than a person directly shopping.

## What SahulatKar records in parallel

A `purchase_executions` row (attempt tracking, screenshot, `merchant_order_id`, `merchant_order_url`), tied back to the originating `orders` row — see [`../07-database/26-database-dictionary.md`](../07-database/26-database-dictionary.md). This is how SahulatKar reconciles "the merchant's order" against "our customer's financing arrangement" — there is no shared identifier or API connecting the two systems; SahulatKar scrapes the merchant's own order confirmation page to capture `merchant_order_id`.

## Why this matters for support and disputes

If a customer later disputes something about delivery or the item received, the *only* record SahulatKar has of what actually happened at the merchant is what the checkout agent scraped (confirmation screenshot, scraped order ID) — there is no API to query the merchant for authoritative order status beyond what a courier tracking number (registered separately with AfterShip) reveals. This is a real operational constraint any dispute-handling process needs to account for — see [`74-merchant-dispute-flow.md`](74-merchant-dispute-flow.md).

## Related documents

[`70-merchant-checkout-flow.md`](70-merchant-checkout-flow.md), [`../07-database/26-database-dictionary.md`](../07-database/26-database-dictionary.md) (`purchase_executions`, `shipments`).
