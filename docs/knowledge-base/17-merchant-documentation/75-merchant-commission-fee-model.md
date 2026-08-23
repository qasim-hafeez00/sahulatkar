# Merchant Commission / Fee Model

**Status:** STABLE (as a confirmed unresolved question, not as a working fee model) — this is the one merchant-documentation topic where something in the data model *does* exist, so it deserves explicit treatment rather than a blanket "not applicable."

## What exists

The `merchants` table carries an `is_affiliate_partner` boolean and a `commission_rate DECIMAL(5,4)` field, for a subset of merchants (currently understood to be the Shopify/Amazon-class stores reachable via the Rye extraction API). See [`../07-database/26-database-dictionary.md`](../07-database/26-database-dictionary.md).

## What is not confirmed

Per [`../02-business-workflows/06-merchant-vendor-journey.md`](../02-business-workflows/06-merchant-vendor-journey.md) and [`../01-company-product/03-business-model.md`](../01-company-product/03-business-model.md), it is **not clear from current engineering documentation** whether:

- This commission represents an actual commercial agreement SahulatKar has with specific merchants, or
- It's inherited entirely from Rye's own merchant/affiliate network (i.e., Rye pays SahulatKar a referral commission as a side effect of using Rye's extraction API, with no direct SahulatKar-merchant relationship at all), or
- It's a schema field added in anticipation of a future capability that was never activated.

## Why this matters

If external-facing materials (investor decks, partnership pitches) describe SahulatKar as having "merchant partnerships" or "affiliate relationships," this field is the only piece of the codebase that could substantiate that claim — and its actual meaning is unconfirmed. **This is the single highest-priority item in the Merchant Documentation category for Business Development to resolve**, since every other document in this folder is confidently "not applicable," while this one is genuinely ambiguous.

## Recommended action

Business Development should confirm: (1) whether `is_affiliate_partner`/`commission_rate` reflects a real, named commercial relationship today, (2) if so, with which merchants and under what terms, and (3) update this document with the answer — replacing "unconfirmed" with either a real commission structure or a statement that the field is currently unused/vestigial.

## Related documents

[`../01-company-product/03-business-model.md`](../01-company-product/03-business-model.md), [`../02-business-workflows/06-merchant-vendor-journey.md`](../02-business-workflows/06-merchant-vendor-journey.md), [`../21-business-merchant-operations/`](../21-business-merchant-operations/).
