# Merchant Pricing Model

**Status:** STABLE — not applicable. SahulatKar does not price merchants for platform access or transaction fees, since there is no merchant account to price.

## Why

SahulatKar's revenue comes entirely from the customer-facing Murabaha profit margin (see [`../01-company-product/03-business-model.md`](../01-company-product/03-business-model.md)), not from any merchant-side fee. Merchants receive full price for whatever they sell — SahulatKar pays it in full via the VCN, exactly as any retail customer would, with no discount, rebate, or fee arrangement negotiated.

## Distinguish from the "commission" concept

The `commission_rate` field on `merchants` (see [`../17-merchant-documentation/75-merchant-commission-fee-model.md`](../17-merchant-documentation/75-merchant-commission-fee-model.md)) is the inverse of a pricing model — if it represents anything real, it's a commission SahulatKar *receives* (from Rye or an affiliate arrangement), not a fee SahulatKar *charges* the merchant. This document exists specifically to keep that distinction clear, since "merchant pricing model" could otherwise be misread as implying the reverse relationship.

## Related documents

[`../17-merchant-documentation/75-merchant-commission-fee-model.md`](../17-merchant-documentation/75-merchant-commission-fee-model.md), [`../01-company-product/03-business-model.md`](../01-company-product/03-business-model.md).
