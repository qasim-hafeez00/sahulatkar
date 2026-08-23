# Reversal Rules

**Status:** STABLE (the distinction this document exists to draw) — the mechanism itself (ledger `reverse` entry endpoint) exists; policy for when to use it is thin.

## Reversal vs. refund — a distinction worth being precise about

A **refund** is customer-facing: money returned to a customer's payment method. A **reversal** is ledger-internal: a correcting journal entry that undoes or corrects a prior journal entry, which may or may not correspond to any customer-facing money movement at all (e.g., correcting a data-entry error in how a payment was categorized, with no money actually moving). Conflating the two in policy or communication is a common source of confusion — this document exists specifically to keep them separate.

## What exists

`POST` reverse-entry functionality on journal entries is referenced in the Ledger Service's API surface (journal entry list/detail/manual-entry/**reverse**, per `docs/System-md-files/M10-M12-delivery-ledger-admin.md`). This is a ledger-correction tool, used by Finance to fix a booking error — not a customer-facing action.

## When a reversal is appropriate (proposed policy — not documented elsewhere)

- A journal entry was posted with an incorrect amount, account, or entry type due to a data or code bug.
- An event was processed twice due to a webhook-deduplication gap (`GW-BL-13`), double-posting a transaction that needs one instance reversed.
- A chargeback (once implemented, see [`../02-business-workflows/54-chargeback-dispute-workflow.md`](../02-business-workflows/54-chargeback-dispute-workflow.md)) requires reversing previously recognized revenue.

## What a reversal should never be used for

Undoing a legitimate refund's accounting — that should be its own distinct `refund`-type entry (per the `journal_entries.entry_type` schema, which already lists `refund` as a separate value from any reversal concept), not a reversal of the original sale entry. Keeping these distinct preserves an accurate audit trail of "what actually happened" (a sale, then separately a refund) rather than making it look like the sale never occurred.

## Related documents

[`106-refund-rules.md`](106-refund-rules.md), [`../20-ledger-accounting/113-ledger-invariants.md`](../20-ledger-accounting/113-ledger-invariants.md).
