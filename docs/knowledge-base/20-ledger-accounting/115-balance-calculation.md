# Balance Calculation

**Status:** STABLE (design) — fallback gap flagged.

## Design

Account balances are **derived**, not stored as a mutable field — computed by summing posted `journal_entry_lines` for a given account (debits minus credits, or credits minus debits, depending on the account's `normal_balance`). A `BalanceSnapshotWorker` is designed to precompute and cache these for performance, since summing every historical line on every balance query would not scale.

## Known gap

If `BalanceSnapshotWorker` fails to run for a given period, the snapshot becomes stale and **there is no confirmed fallback to recalculate the true balance on-the-fly** (`LS-BL-03`). This means a balance query during a snapshot outage could silently return a stale (and therefore wrong) figure rather than either the correct real-time figure or an explicit error — the worst of the three options, since it looks correct without being correct.

## Recommended fix pattern

A balance-calculation endpoint should either (a) always compute from raw journal lines when no fresh snapshot exists, accepting the performance cost for that specific query, or (b) explicitly flag the response as stale-snapshot-derived so a caller (e.g., an admin dashboard) can decide whether to trust it — silently serving a stale number with no indication is the option to avoid.

## Relationship to `available_credit`

This ledger-level balance calculation is architecturally distinct from `users.available_credit` (a Credit Engine/Gateway-owned figure, not a ledger-derived balance) — the two should not be confused. `available_credit`'s own known gap (`GW-BL-01`, not decremented at order initiation) is a separate bug in a separate system, documented in [`../03-bnpl-financing/15-credit-limit-rules.md`](../03-bnpl-financing/15-credit-limit-rules.md).

## Related documents

[`113-ledger-invariants.md`](113-ledger-invariants.md), [`117-financial-reporting.md`](117-financial-reporting.md).
