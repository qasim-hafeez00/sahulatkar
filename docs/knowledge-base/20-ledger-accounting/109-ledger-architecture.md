# Ledger Architecture

**Status:** STABLE (design) — critical enforcement gap flagged prominently, since it undermines the architecture's core promise.

## Design

A dedicated Ledger Service owns double-entry bookkeeping as its sole responsibility — no other service writes directly to `journal_entries`/`journal_entry_lines`; they publish events (or make internal calls) that the Ledger Service translates into entries. This is the correct architectural pattern for financial system-of-record isolation: any service can *cause* a financial event, but only one service *records* it.

## Layers

```
Event/call ingestion (from Gateway, Payment Orchestrator, Notification Service)
  ↓
Journal entry construction (source_type/source_id polymorphic linkage back to the originating record)
  ↓
Journal entry posting (debit/credit lines against the chart of accounts)
  ↓
Balance calculation (derived from posted entries)
  ↓
Financial reporting (trial balance, balance sheet, income statement, cash flow)
```

## The architecture's core promise, and why it's currently broken

The entire point of double-entry bookkeeping is that `total_debit == total_credit` on every entry, always — this is what makes the ledger self-checking and trustworthy. **Per the 2026-04-27 audit (`LS-CRIT-02`), this invariant is not actually validated anywhere in the current posting code.** This is not a minor implementation detail — it means the architecture's central guarantee doesn't currently hold, and any financial report generated from the ledger today should be treated as unverified until this is fixed. See [`113-ledger-invariants.md`](113-ledger-invariants.md).

## The `loan.created` gap, from this document's specific angle

Because no service currently publishes `loan.created` (see [`../02-business-workflows/07-bnpl-workflow-e2e.md`](../02-business-workflows/07-bnpl-workflow-e2e.md)), the ledger architecture described above has never actually ingested the single most important event type it exists to record — the creation of a financing receivable. Every other document in this knowledge base that mentions this gap is describing the same root cause from a different angle; this document names it as an *architectural* failure specifically: the ingestion layer has a confirmed hole at its most important input.

## Related documents

[`110-chart-of-accounts.md`](110-chart-of-accounts.md), [`111-double-entry-accounting-model.md`](111-double-entry-accounting-model.md), [`113-ledger-invariants.md`](113-ledger-invariants.md), [`../05-architecture/microservices/ledger-service.md`](../05-architecture/microservices/ledger-service.md).
