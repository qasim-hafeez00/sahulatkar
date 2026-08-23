# Merchant Settlement Flow

**Status:** STABLE — there is none. Full explanation: [`../02-business-workflows/11-merchant-settlement-reconciliation.md`](../02-business-workflows/11-merchant-settlement-reconciliation.md).

## Summary

SahulatKar pays the merchant in full, immediately, at the moment of checkout — via the VCN, exactly as any retail customer's card would settle at point of sale. There is no deferred payment to the merchant, no settlement batch, no settlement schedule, and therefore nothing to reconcile *with the merchant*. What SahulatKar reconciles instead is its own inbound collections (down payments and installments) against what its payment gateways (Safepay/JazzCash/EasyPaisa) report — a completely different reconciliation problem, covered in [`../02-business-workflows/11-merchant-settlement-reconciliation.md`](../02-business-workflows/11-merchant-settlement-reconciliation.md).

## Related documents

[`../02-business-workflows/11-merchant-settlement-reconciliation.md`](../02-business-workflows/11-merchant-settlement-reconciliation.md), [`65-merchant-overview.md`](65-merchant-overview.md).
