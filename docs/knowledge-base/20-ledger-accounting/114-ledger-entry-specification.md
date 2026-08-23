# Ledger Entry Specification

**Status:** STABLE — the field-level shape of a journal entry, for anyone writing code that posts to the ledger.

## Header (`journal_entries`)

| Field | Purpose |
|---|---|
| `entry_number` | Human-readable identifier, e.g. `JE-2025-0001234` |
| `entry_date` | The accounting date this entry applies to (may differ from `created_at`) |
| `description` | Free-text explanation |
| `entry_type` | One of the enum values in [`112-transaction-types.md`](112-transaction-types.md) |
| `source_type` / `source_id` | Polymorphic reference back to the originating record (e.g., `source_type='loan'`, `source_id=<loans.id>`) — this is what lets an entry be traced back to the business event that caused it |
| `is_balanced` | Should be `TRUE` only if `total_debit == total_credit` — **currently not actually validated at write time**, see [`113-ledger-invariants.md`](113-ledger-invariants.md) |
| `total_debit` / `total_credit` | Sum of the corresponding lines |

## Lines (`journal_entry_lines`)

| Field | Purpose |
|---|---|
| `journal_id` | FK to the header |
| `account_id` | FK to `ledger_accounts` — **should be validated to exist before posting; currently isn't** (`LS-BL-01`), causing a raw DB error on an invalid code instead of a clean rejection |
| `debit_amount` / `credit_amount` | Exactly one is > 0 per line — enforced by a schema constraint |

## Minimum required lines per entry

At least two lines (one debit, one credit) — a single-line entry would violate double-entry bookkeeping by definition and should be rejected outright, though whether the application layer actually enforces "at least 2 lines" as distinct from "debit=credit" is not explicitly confirmed in the reviewed source.

## Traceability requirement

Every entry should be traceable to a specific business event via `source_type`/`source_id` — an entry with no source reference (or a `source_type='manual'` entry with no linked justification beyond free-text `description`) should be a rare, auditable exception (e.g., a genuine correcting entry), not a routine pattern.

## Related documents

[`112-transaction-types.md`](112-transaction-types.md), [`113-ledger-invariants.md`](113-ledger-invariants.md), [`../07-database/26-database-dictionary.md`](../07-database/26-database-dictionary.md).
