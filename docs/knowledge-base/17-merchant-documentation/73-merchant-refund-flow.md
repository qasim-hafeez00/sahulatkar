# Merchant Refund Flow

**Status:** PLANNED / open policy question — see [`../02-business-workflows/56-merchant-refund-workflow.md`](../02-business-workflows/56-merchant-refund-workflow.md) for the full detail. This document is a short pointer, kept separate to fill the "Merchant Documentation" category's expected slot.

## Summary

When a customer returns a product to the merchant that sold it, the merchant refunds SahulatKar's payment instrument (the VCN, if still active) or a subsequent manual refund path — not the customer directly, since SahulatKar was the purchaser of record. SahulatKar must then separately refund/adjust the customer's own obligation. Neither the detection of a merchant-side refund nor the customer-side adjustment (`RefundOrchestrator`) is implemented today. The unresolved policy question — who absorbs the cost when a merchant refuses to accept a return from a third-party purchaser at all — is a genuine open item for Legal/Product, not an engineering gap.

## Related documents

[`../02-business-workflows/56-merchant-refund-workflow.md`](../02-business-workflows/56-merchant-refund-workflow.md) (full detail), [`../02-business-workflows/09-refund-cancellation-workflow.md`](../02-business-workflows/09-refund-cancellation-workflow.md).
