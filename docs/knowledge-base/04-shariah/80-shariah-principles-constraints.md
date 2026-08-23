# Shariah Principles & Constraints

> **STATUS: INTERNAL DRAFT.** Same caveat as every document in this folder: not reviewed by a qualified Shariah board. This document lists the *principles the platform's design appears to be built against*, inferred from the contract structure and enforced rules — not an independently sourced statement of Islamic finance principles.

## Principles the design appears to target

1. **Riba (interest) avoidance.** No interest is charged; financing is structured as a cost-plus sale (Murabaha) with a fixed profit disclosed at signing, not an accruing interest rate.
2. **Gharar (excessive uncertainty) minimization.** Cost price, profit amount, and total repayable must all be disclosed and fixed before signing — enforced via `NOT NULL` constraints, not left to be determined later. The ±5% Wakalah price-variance tolerance is a specific, bounded allowance for exactly the kind of uncertainty that would otherwise be a compliance concern — see the open question on this in [`17-shariah-product-structure.md`](17-shariah-product-structure.md).
3. **Asset-backed transaction.** The financing is tied to a specific, real, physically delivered product — not a cash loan. This is why the Wakalah/Murabaha two-step structure exists rather than a simpler "lend then repay with a fee" model.
4. **No penalty profit (late fees not retained).** A stipulated late fee exists as a payment-discipline mechanism, but 100% is charity-routed rather than retained as platform income — a design choice specifically to avoid the fee functioning as disguised interest on late payment.
5. **Prohibited goods exclusion.** Financing is not extended for alcohol, tobacco, gambling, adult content, weapons, or interest-bearing instruments — checked before any offer, not left to the customer's discretion.

## Constraints these principles impose on the platform's design

- The Murabaha sale price **cannot change after signing** — this is a hard Shariah constraint on cost-plus-sale contracts generally (the "cost-plus" figure must be fixed at the point of sale), which is why [`../03-bnpl-financing/12-bnpl-product-specification.md`](../03-bnpl-financing/12-bnpl-product-specification.md) states that a payment restructuring must be modeled as a new agreement/addendum, not a mutation of the original.
- Ownership must genuinely transfer to SahulatKar (via the Wakeel's purchase) before it can be resold to the customer — the two-contract Wakalah-then-Murabaha sequence exists specifically to satisfy this, rather than a single simultaneous transaction.
- Any late-fee mechanism must not function as disguised interest — the charity-routing design is the platform's answer to this constraint, though **whether a stipulated (even charity-routed) late fee is itself permissible is one of the open board questions in [`17-shariah-product-structure.md`](17-shariah-product-structure.md)**, not a settled matter.

## What this document does not do

It does not cite primary Shariah sources (Quranic verses, hadith, specific AAOIFI standard clauses) — that sourcing work belongs to the actual Shariah board review, not to engineering-derived documentation. This document exists to make explicit *what the engineering team appears to have understood* it was building toward, so the board has a clear starting point for validation or correction.

## Related documents

[`17-shariah-product-structure.md`](17-shariah-product-structure.md), [`81-shariah-compliance-requirements.md`](81-shariah-compliance-requirements.md).
