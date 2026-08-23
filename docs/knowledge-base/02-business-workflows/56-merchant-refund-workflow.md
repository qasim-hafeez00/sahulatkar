# Merchant Refund Workflow

**Status:** PLANNED / N/A-framed — there is no merchant-initiated refund path in this model (merchants have no account to initiate anything from), and the customer-initiated refund path this would otherwise feed into is itself unimplemented. See both caveats below.

## Why this differs from a typical BNPL "merchant refund" workflow

In merchant-network BNPL, a merchant-initiated refund is common: the merchant processes a return and notifies the BNPL provider, which then adjusts or cancels the customer's remaining installments. **SahulatKar has no merchant relationship to receive such a notification from.** If a customer returns a product to a third-party site, that site refunds *SahulatKar's payment card* (the VCN, if still active, or a manual refund to whatever payment method was used) — SahulatKar has no automated way to detect that this happened unless it separately reconciles VCN issuer transaction data.

## What would need to exist (none of it does today)

1. **Detection:** either the customer reports "I returned this," or a VCN-issuer-side refund transaction is detected via reconciliation (which itself runs on mock data today — see [`11-merchant-settlement-reconciliation.md`](11-merchant-settlement-reconciliation.md)).
2. **Verification:** confirm the return was genuinely accepted and refunded by the third-party site — not just claimed by the customer.
3. **Customer-side adjustment:** cancel/reduce the customer's remaining installment obligations proportionally, and refund whatever the customer already paid toward this loan (down payment + any installments) — this requires `RefundOrchestrator` to actually be implemented (`PO-CRIT-01`, currently a stub).
4. **Ledger correction:** reverse the recognized Murabaha profit associated with the cancelled portion.

## The harder, undocumented policy question

What happens when the merchant **refuses** the return? Per [`06-merchant-vendor-journey.md`](06-merchant-vendor-journey.md), this is a real risk of the vendor-agnostic model (SahulatKar isn't the merchant's customer of record) and is currently an open policy question for Product/Legal, not just an engineering gap — does SahulatKar absorb the cost, does the customer remain obligated on the loan for a product they've returned to a merchant who won't accept it, or is there a documented cap on how much exposure SahulatKar will absorb before declining to support returns to a given merchant?

## Related documents

[`06-merchant-vendor-journey.md`](06-merchant-vendor-journey.md), [`09-refund-cancellation-workflow.md`](09-refund-cancellation-workflow.md), [`../17-merchant-documentation/73-merchant-refund-flow.md`](../17-merchant-documentation/73-merchant-refund-flow.md).
