# Ledger Service

**Status:** STABLE (design) — ~65% complete per audit, blocked by cash-flow statement, charity disbursement, and auto-collection gaps.

## Purpose

The system's financial system of record: double-entry bookkeeping, the daily billing sweep that identifies due/overdue installments, charity routing for late fees, and financial reporting.

## Responsibilities

- Double-entry journal entries (`journal_entries` / `journal_entry_lines`), chart of accounts.
- Daily billing sweep (`BillingSweepWorker`, `pg_cron` 08:00) over a partial index sized for 100K rows in under 60 seconds.
- Charity routing: `late_fee_charity_allocations`, intended to be immutable once disbursed.
- Financial statements: trial balance, balance sheet, income statement, cash flow (stub), Shariah compliance report.
- Accounting period management (open/close periods).

## Dependencies

PostgreSQL, Redis (event listening for `payment.confirmed` and, in the intended design, `loan.created`).

## Key APIs

`GET /admin/finance/pl`, `GET /admin/finance/reconciliation`, `GET /admin/finance/shariah-report`, journal entry list/detail/manual-entry/reverse, period management. Full spec: `docs/System-md-files/M10-M12-delivery-ledger-admin.md` (M11 section).

## Database ownership

`ledger_accounts`, `journal_entries`, `journal_entry_lines`, `late_fee_charity_allocations`.

## Chart of accounts (seed)

```
ASSETS:    1001 Cash/Bank | 1100 AR-Installments | 1200 VCNs Issued
LIABILITY: 2001 AP-Merchants | 2100 Charity Payable | 2200 Customer Deposits
EQUITY:    3001 Owner Equity | 3900 Retained Earnings
REVENUE:   4001 Murabaha Profit | 4002 Affiliate Commission | 4003 Late Fee Collections
EXPENSE:   5001 COGS-Merchant Payment | 5002 Gateway Fees | 5003 VCN Issuance | 5004 Loan Loss Provision
```

## Known gaps (from `docs/PRODUCTION_GAPS_REPORT.md` §5)

- **LS-CRIT-02 (critical):** journal entries are posted **without validating debits = credits** — the core double-entry invariant is not actually enforced in code, meaning the general ledger can become unbalanced.
- **LS-CRIT-03 (high, Shariah-relevant):** charity fund disbursement is a stub — late fees are accrued but never actually disbursed or posted to the GL. Given [`../../04-shariah/17-shariah-product-structure.md`](../../04-shariah/17-shariah-product-structure.md) makes charity routing a core Shariah-compliance mechanism, this is not just an accounting gap.
- **LS-CRIT-04 (critical):** billing sweep detects overdue installments but has no mechanism to trigger actual auto-collection via Payment Orchestrator.
- **LS-CRIT-01 (critical):** cash flow statement generation is a stub (headers only).
- **LS-CRIT-05 (high):** failed ledger events go to a dead-letter queue with no consumer — they accumulate indefinitely with no retry or alerting.
- **Cross-service:** never receives the `loan.created` event it needs to post initial liability/receivable entries for any loan — see [`../../02-business-workflows/07-bnpl-workflow-e2e.md`](../../02-business-workflows/07-bnpl-workflow-e2e.md).
- Full checklist: `docs/PRODUCTION_GAPS_REPORT.md` §5, §13.
