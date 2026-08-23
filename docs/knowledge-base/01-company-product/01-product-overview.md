# Product Overview

**Status:** STABLE · **Read this first**, then [`MASTER_SPEC.md`](../00-master-spec/MASTER_SPEC.md) for the full map.

## What is SahulatKar?

SahulatKar is Pakistan's first vendor-agnostic, Shariah-structured Buy-Now-Pay-Later platform. A customer pastes a link to any product on any online store; an AI agent buys it on their behalf; the customer repays SahulatKar in installments under an Islamic Murabaha (cost-plus-sale) contract.

The core mechanic that makes this different from every merchant-network BNPL provider: **SahulatKar never integrates with the merchant.** It behaves like a retail customer — signs into the store, adds to cart, checks out with a payment card — except the "customer" doing the shopping is an autonomous browser agent, and the "card" is a single-use virtual card number (VCN) issued only after the real customer has signed a financing contract and paid a down payment.

## What problem are we solving?

Two problems, addressed together:

1. **Merchant-network BNPL only covers merchants who integrated.** Most of what a Pakistani shopper actually wants — global e-commerce, small independent stores, marketplaces — has no local BNPL integration. A vendor-agnostic model removes that ceiling entirely: coverage is "any URL," not "any of our partner merchants."
2. **Most Pakistani consumers are thin-file.** They lack the traditional credit bureau history conventional lenders require, and many additionally want a financing product that is Shariah-compliant (no interest). SahulatKar's credit engine leans on alternative data (device signals, KYC verification quality, behavioral velocity, telco data) instead of requiring bureau history, and structures the product as Murabaha instead of an interest-bearing loan.

## Who are our users?

Individual Pakistani consumers, phone-verified (E.164 `+92` numbers), 18+ (hard-blocked below), who want to purchase a specific product they can't pay for in full today. See [`04-product-glossary.md`](04-product-glossary.md) and [`../02-business-workflows/05-customer-journey-e2e.md`](../02-business-workflows/05-customer-journey-e2e.md) for the full lifecycle they move through.

## Who are our "merchants"?

There is no merchant-facing product. "Merchants" in SahulatKar's data model are simply the arbitrary third-party websites the checkout agent transacts with — the merchant has no account, no integration, and (in the general case) no idea the purchaser is a BNPL platform's agent rather than an ordinary customer. A subset are tracked as recognized "affiliate partners" (currently the Shopify/Amazon-class stores reachable via the Rye extraction API) with a commission rate and a measured checkout success rate, purely for internal routing and reliability purposes — this tracking requires no participation from the merchant. See [`../02-business-workflows/06-merchant-vendor-journey.md`](../02-business-workflows/06-merchant-vendor-journey.md) for the operational implications (returns, account bans, disputes) of this model.

## What exactly is BNPL in our system?

An Agency Murabaha structure, not an interest-bearing loan:

1. The customer signs a **Wakalah Agreement** appointing SahulatKar as their purchasing agent (*Wakeel*) for a specific product at an authorized amount.
2. SahulatKar's agent buys the product using a single-use virtual card.
3. SahulatKar sells the procured product to the customer via a **Murabaha Contract** at cost plus a disclosed, fixed profit margin, with a fixed installment schedule.
4. The customer repays in equal biweekly installments until the total repayable amount is paid off.

Full detail: [`../03-bnpl-financing/12-bnpl-product-specification.md`](../03-bnpl-financing/12-bnpl-product-specification.md) and [`../04-shariah/17-shariah-product-structure.md`](../04-shariah/17-shariah-product-structure.md) *(internal draft, pending Shariah board review)*.

## How does SahulatKar make money?

Primarily the disclosed Murabaha profit margin on each purchase (currently tiered by plan length in the codebase — 2.5%/4.0%/7.0% for pay-in-3/4/6 — though this specific tiering has not yet received written Shariah board sign-off, a confirmed open compliance item). Late fees are calculated on overdue installments but 100% of collected late fees are routed to charity (Edhi Foundation) — SahulatKar retains none of it by design. Full breakdown: [`03-business-model.md`](03-business-model.md).

## What makes SahulatKar different?

- **Universal coverage** — works on any product URL, not a merchant network.
- **Purchasing agent + financier in one** — most BNPL providers are pure financiers sitting on top of someone else's checkout; SahulatKar's agent *is* the checkout.
- **Shariah-structured by design**, not retrofitted — cost-price disclosure and charity-routed late fees are enforced at the database schema level (`NOT NULL` constraints, dedicated allocation tables), not just in policy documents.
- **AI-automated purchase execution** — a self-healing Playwright agent (with GPT-4o Vision fallback for UI recovery) handles the actual checkout, with human-in-the-loop escalation when automation can't complete it.

## What is our long-term vision?

See [`02-product-vision.md`](02-product-vision.md).

## Current build status

As of the most recent code-verified audit (`docs/PRODUCTION_GAPS_REPORT.md`, 2026-04-27), the platform is **~55% complete overall**: backend services are 60–85% built depending on service, the admin frontend is ~10% (mock data, shells only), and the customer frontend is ~2% (scaffold only). Several pieces described above as the target design — most notably automated checkout completion and refunds — are not yet functional end-to-end. This document describes what SahulatKar *is designed to be*; see [`MASTER_SPEC.md` §25](../00-master-spec/MASTER_SPEC.md#25-failure-scenarios-current-known) for the gap between design and current reality.
