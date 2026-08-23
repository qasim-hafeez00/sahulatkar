# Shariah Product Structure

> **STATUS: INTERNAL DRAFT.** This document describes the Shariah contractual structure *as currently implemented in engineering specifications and code* (`docs/System-md-files/M05-contracts.md`, `pricing_service.py`, the `wakalah_agreements`/`murabaha_contracts` schemas). It has **not** been reviewed, validated, or certified by a qualified Shariah advisory board. It is not a fatwa, not a compliance certification, and must not be represented externally as "Shariah-certified" or "Shariah-approved" until the open questions below are formally resolved.
>
> **Open questions requiring Shariah board review:**
> - [ ] Confirm the Agency Murabaha structure (Wakalah + Murabaha, as described below) is sound as implemented, not just as designed on paper.
> - [ ] Confirm/reject the tiered markup structure (2.5%/4.0%/7.0% by plan length) — flagged in code (`pricing_service.py:22`) as awaiting written sign-off. This is a confirmed open item, not a hypothetical.
> - [ ] Confirm the late-fee-to-charity structure satisfies Shariah requirements around penalty clauses in a sale contract, including the specific charity recipient (Edhi Foundation) and the mechanism (is a *stipulated* late fee, even if charity-routed, itself permissible, and under what conditions).
> - [ ] Confirm the ±5% price-variance tolerance on Wakalah-authorized purchases doesn't create gharar (excessive uncertainty) concerns.
> - [ ] Confirm ownership-transfer timing ("upon physical delivery confirmation," per the Murabaha template) is correctly structured relative to when SahulatKar's Wakeel takes possession.
> - [ ] Confirm whether AAOIFI Shariah Standard No. 8 (cited in engineering docs as the legal basis) is the correct standard for this specific agency-Murabaha implementation, and whether local Pakistani Shariah Board guidance layers additional requirements.

## What contractual structure is used

**Agency Murabaha**, in two sequential contracts:

1. **Wakalah Agreement.** The customer appoints SahulatKar as *Wakeel* (agent) to purchase a specific, named product from a specific merchant, at an authorized amount (with a ±5% price-variance tolerance). This contract authorizes the purchase; it does not itself create a financing obligation.
2. **Murabaha Contract.** Once the Wakeel has procured (or is procuring) the product, SahulatKar sells it to the customer at cost price plus a disclosed, fixed profit margin. This contract fixes the sale price and installment schedule at signing — neither can change afterward.

## Who is buying, who is selling

- Under the Wakalah, SahulatKar acts as the customer's agent when purchasing from the third-party website ("merchant" in SahulatKar's terminology — see [`../02-business-workflows/06-merchant-vendor-journey.md`](../02-business-workflows/06-merchant-vendor-journey.md)).
- Under the Murabaha, SahulatKar is the seller and the customer is the buyer, for the *resale* of the already-procured item at cost-plus-profit.

## What is the underlying transaction

One product purchase, financed via deferred payment, structured to avoid an interest-bearing loan: instead of lending cash and charging interest, SahulatKar buys the specific asset and resells it at a transparent markup, repaid over time.

## Where SahulatKar makes a profit

The disclosed Murabaha profit margin only (see [`../01-company-product/03-business-model.md`](../01-company-product/03-business-model.md) for the specific rates and their approval status). Explicitly **not** from late fees — those are 100% charity-routed by design, enforced via a database trigger (`fn_apply_late_fee()`) that creates a `late_fee_charity_allocations` record, not a revenue-recognition entry.

## Three Shariah rules enforced at the database level

These are described in engineering docs as immutable and CI-tested — a meaningful signal of intent, though database enforcement is not itself a substitute for Shariah board sign-off on the underlying design:

1. **Late Fee → Charity.** Trigger-enforced. Zero retained by the platform.
2. **Cost Price Disclosure.** `murabaha_contracts.cost_price`, `profit_amount`, and `profit_rate_pct` are all `NOT NULL` — a contract literally cannot be generated without complete disclosure of all three.
3. **Prohibited Categories.** Alcohol, tobacco, gambling, adult content, weapons, and interest-bearing instruments are blocked at the product-extraction stage, before any financing offer exists. All blocks logged to an immutable, append-only `prohibited_items_log`.

## Legal basis cited in engineering documentation

SECP Islamic Finance Guidelines 2023, AAOIFI Shariah Standard No. 8, and (for the electronic contract/signature mechanism) the Electronic Transactions Ordinance 2002 Section 15. **Not independently verified against current SECP/AAOIFI text as part of this documentation pass** — Legal/Compliance should confirm citation accuracy before external use.

## Related documents

[`18-shariah-governance.md`](18-shariah-governance.md), [`19-shariah-review-register.md`](19-shariah-review-register.md), [`../03-bnpl-financing/12-bnpl-product-specification.md`](../03-bnpl-financing/12-bnpl-product-specification.md), [`../11-compliance/36-compliance-requirements-matrix.md`](../11-compliance/36-compliance-requirements-matrix.md).
