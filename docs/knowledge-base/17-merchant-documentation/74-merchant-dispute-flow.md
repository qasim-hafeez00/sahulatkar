# Merchant Dispute Flow

**Status:** PLANNED — a "dispute" in this context (the merchant disputing/blocking/refusing to honor a transaction it perceives as suspicious or third-party) has no documented handling process, distinct from a customer disputing a charge (see [`../02-business-workflows/54-chargeback-dispute-workflow.md`](../02-business-workflows/54-chargeback-dispute-workflow.md)).

## What "merchant dispute" means specifically in this model

Because SahulatKar's checkout agent transacts as an anonymous retail customer with no ongoing relationship to the merchant, the merchant has no formal channel to "dispute" anything with SahulatKar directly — there's no merchant support contact, no partner-dispute process, no shared case-management system. What actually happens instead:

- **The merchant's own systems block or reverse the transaction** (fraud detection flags the purchasing pattern, the card is declined post-authorization, or the order is cancelled by the merchant after the fact) — this surfaces to SahulatKar as a failed or reversed purchase execution, handled operationally per [`../12-operations/40-merchant-vendor-support-sop.md`](../12-operations/40-merchant-vendor-support-sop.md), not as a formal "dispute case."
- **The merchant refuses a return** — covered in [`73-merchant-refund-flow.md`](73-merchant-refund-flow.md), an open policy question rather than a process.
- **The merchant's own customer-service channel is contacted** (e.g., by SahulatKar's HITL operator posing as the purchasing customer, if a manual intervention requires it) — this is ad hoc today, not a documented SOP.

## Recommended action

If merchant-initiated transaction blocks/reversals become a frequent enough occurrence to warrant tracking (see the merchant-ban-rate monitoring gap noted in [`../12-operations/40-merchant-vendor-support-sop.md`](../12-operations/40-merchant-vendor-support-sop.md)), this document should be expanded from a policy placeholder into an actual operational SOP with defined detection and response steps.

## Related documents

[`../12-operations/40-merchant-vendor-support-sop.md`](../12-operations/40-merchant-vendor-support-sop.md), [`../02-business-workflows/54-chargeback-dispute-workflow.md`](../02-business-workflows/54-chargeback-dispute-workflow.md).
