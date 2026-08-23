# Refund SOP

**Status:** PLANNED — there is currently no system-supported refund pathway (`RefundOrchestrator` is a stub). This SOP describes the **manual interim process** staff must use until it's built, since customers will ask for refunds regardless of what's implemented.

## Interim manual process (until `RefundOrchestrator` exists)

1. Confirm the refund is warranted per whatever policy exists at the time (see [`../19-payments-financial-operations/106-refund-rules.md`](../19-payments-financial-operations/106-refund-rules.md) for the proposed rules — not yet formally approved policy, but a reasonable starting reference).
2. Process the refund **directly through the relevant payment gateway's own merchant portal** (Safepay/JazzCash/EasyPaisa each have their own dashboard-level refund capability, independent of SahulatKar's own system) — this is the only way to actually return money to the customer today.
3. Manually create a corresponding ledger correction entry (via the manual journal-entry capability, coordinated with Finance) — since the system won't do this automatically.
4. Manually adjust the customer's loan/installment records to reflect the refund — e.g., mark the down payment as refunded, cancel the loan if the whole order is being reversed. **This step requires direct database or admin-tool intervention and should be done carefully, with Finance/Engineering involved**, since there's no built-in workflow to do it safely.
5. Notify the customer manually (no automated refund-confirmation notification exists).

## Why this SOP exists despite describing manual work

Customers don't wait for engineering roadmaps — a documented, careful manual process is safer than either refusing all refunds or improvising a different ad hoc process each time. This SOP should be replaced with a much simpler "use the system" procedure the moment `RefundOrchestrator` ships.

## Related documents

[`../02-business-workflows/09-refund-cancellation-workflow.md`](../02-business-workflows/09-refund-cancellation-workflow.md), [`../19-payments-financial-operations/106-refund-rules.md`](../19-payments-financial-operations/106-refund-rules.md).
