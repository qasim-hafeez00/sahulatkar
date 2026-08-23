# Payment Failure SOP

**Status:** STABLE — operational procedure for staff handling a customer-reported or system-flagged payment failure, complementing the technical detail in [`../19-payments-financial-operations/103-failed-payment-handling.md`](../19-payments-financial-operations/103-failed-payment-handling.md).

## When a customer reports "my payment failed" or "I was charged but it shows as failed"

1. Check `payment_transactions` for the relevant order/installment — look at `status`, `failure_code`, `failure_message`, and `gateway_txn_id`.
2. If the gateway's own portal shows the charge succeeded but SahulatKar's record shows `failed` or `pending` — this is likely the uncompensated-transaction gap (`PO-BL-03`/`GW-BL-06`) rather than an actual customer-side failure. **Do not tell the customer to simply retry** in this case — retrying could result in a genuine double-charge. Escalate to Engineering/Finance to manually reconcile first.
3. If both SahulatKar's record and the gateway agree the charge failed — proceed with standard retry guidance to the customer, or process a manual payment record (`POST /payments/manual-record`) if the customer has proof of payment via another channel (bank deposit, etc.).

## Known gap to be aware of

No dedicated customer-initiated retry endpoint currently exists for a failed installment payment (`GW-GAP-10`) — staff should guide the customer through the standard payment screen rather than promising a "retry" button that doesn't exist yet.

## When to escalate to Finance vs. handle directly

Handle directly: a straightforward declined card/insufficient funds, customer wants to retry with a different method. Escalate to Finance: any case where SahulatKar's and the gateway's records disagree, or where a duplicate charge is suspected.

## Related documents

[`../19-payments-financial-operations/103-failed-payment-handling.md`](../19-payments-financial-operations/103-failed-payment-handling.md), [`../02-business-workflows/53-missed-payment-workflow.md`](../02-business-workflows/53-missed-payment-workflow.md).
