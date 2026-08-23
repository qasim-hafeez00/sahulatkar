# Merchant Settlement / Payment-Gateway Reconciliation

**Status:** STABLE (explains why this document is scoped differently than a typical BNPL "merchant settlement" doc) — implementation gap flagged inline.

## Why there is no merchant settlement

In merchant-network BNPL, the platform fronts money to the merchant and settles with them on a schedule (e.g., T+2, minus a fee). **SahulatKar has no such relationship.** It pays the merchant in full, immediately, at checkout — via the VCN, exactly like any retail customer's card. There is nothing to settle with the merchant afterward, because nothing was deferred on the merchant's side. See [`06-merchant-vendor-journey.md`](06-merchant-vendor-journey.md) for why this model was chosen and what it costs operationally.

## What actually gets reconciled: SahulatKar's own gateway settlement

What SahulatKar must reconcile is the *inbound* side: what Safepay and JazzCash/EasyPaisa report they collected from customers (down payments and installments) against what actually lands in SahulatKar's own bank account, and against SahulatKar's internal `payment_transactions` ledger.

| Gateway | Settlement timing | Reconciliation source |
|---|---|---|
| Safepay | T+2 | Settlement file / API |
| JazzCash | T+1 | SFTP settlement file |
| EasyPaisa | T+1 | Settlement file / API |
| Raast | T+0 (Phase 4, not yet live) | N/A |

## Reconciliation process (target design)

1. Daily/scheduled pull of each gateway's settlement report.
2. Match each settled transaction to a `payment_transactions` record by `gateway_txn_id`.
3. Flag discrepancies (amount mismatch, missing settlement, missing internal record).
4. Post reconciliation results to the Ledger Service; surface via `GET /admin/finance/reconciliation`.
5. `POST /admin/finance/reconciliation/import` accepts a manually uploaded settlement file as a fallback.

## Known gap (PO-CRIT-02 — critical, from `docs/PRODUCTION_GAPS_REPORT.md`)

As of the last code audit, `reconciliation_worker.py` reads from **mock JSON files on the local filesystem** (`settlement_{gateway}_{date}.json`) rather than a real SFTP connection to JazzCash or a real API call to Safepay. **Financial reconciliation does not function against live data in the current build.** This is a Priority-2 (must-fix-before-scale) item, and arguably should be treated as a launch blocker for any release that handles real customer money, since it is the platform's only check that collected funds actually match what gateways report.

Ledger-side reconciliation additionally only checks that revenue *was posted* at all, not that the *amount* posted matches the corresponding `PaymentTransaction` record (`LS-BL-06`) — a second layer of the same underlying gap.

## Related documents

[`06-merchant-vendor-journey.md`](06-merchant-vendor-journey.md), [`08-payment-workflow.md`](08-payment-workflow.md), [`../07-database/25-database-architecture.md`](../07-database/25-database-architecture.md), `docs/PRODUCTION_GAPS_REPORT.md` §4.
