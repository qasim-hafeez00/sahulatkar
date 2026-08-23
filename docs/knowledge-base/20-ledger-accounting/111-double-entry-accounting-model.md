# Double-Entry Accounting Model

**Status:** STABLE (schema design) — enforcement gap is the central fact of this document.

## The model

Every financial event produces a `journal_entries` header row plus two or more `journal_entry_lines` rows, each hitting exactly one side (debit or credit) of an account — enforced at the schema level by a constraint that a single line cannot have both `debit_amount > 0` and `credit_amount > 0`. The header carries `is_balanced BOOLEAN` and `total_debit`/`total_credit` fields, meaning the schema was explicitly designed with the intent that balance be checked.

## Worked example: a loan being created (target design — currently never happens, see below)

```
DR  1100 AR-Installments        15,600
  CR  2200 Customer Deposits      (reversed once down payment applied)
  CR  4001 Murabaha Profit           600
  CR  1001 Cash/Bank (down payment)  5,000
```

(Illustrative — the exact posting pattern, including revenue-recognition timing for the profit portion, is not explicitly specified in engineering docs; Finance/Accounting should confirm the precise entries against actual accounting policy, not treat this example as authoritative.)

## The gap that makes this model currently theoretical for every loan

Per `LS-CRIT-02`, `is_balanced` and the debit=credit invariant are **not actually validated when an entry is posted** — the schema supports checking it, but the application code doesn't enforce it. Combined with the missing `loan.created` event (see [`109-ledger-architecture.md`](109-ledger-architecture.md)), the practical result is: **no loan currently gets the entries shown in the worked example above at all**, and even the entries that *do* get posted for other event types aren't verified to balance. This document describes the intended accounting model; it should not be read as a description of what the current ledger data actually contains.

## What "fixing this" requires (two independent fixes, often conflated)

1. Publish `loan.created` (Gateway) so entries get created in the first place.
2. Validate debit=credit at posting time (Ledger Service) so the entries that do get created are actually correct. Fixing only one of these leaves the other gap live — both are needed for the model above to be trustworthy.

## Related documents

[`109-ledger-architecture.md`](109-ledger-architecture.md), [`113-ledger-invariants.md`](113-ledger-invariants.md), [`114-ledger-entry-specification.md`](114-ledger-entry-specification.md).
