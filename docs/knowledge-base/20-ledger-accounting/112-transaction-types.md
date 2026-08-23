# Transaction Types

**Status:** STABLE — `journal_entries.entry_type` enum values, with the triggering event and current implementation status for each.

| Entry type | Triggering event | Status |
|---|---|---|
| `payment_received` | Down payment or installment collected | Posting logic exists but debit=credit is unvalidated (`LS-CRIT-02`) |
| `merchant_payment` | VCN charge at checkout | Tied to `purchase_executions`/`virtual_cards` — posting confirmed to exist but not independently verified against the audit's specific findings |
| `refund` | Customer refund issued | **Never exercised** — `RefundOrchestrator` is a stub, so nothing currently triggers this entry type |
| `late_fee` | Overdue installment accrues a fee | Accrual logic exists; the corresponding charity disbursement leg (below) does not |
| `charity_disbursement` | Late fee actually paid out to Edhi Foundation | **Stub — never actually posted** (`LS-CRIT-03`) |
| `provision` | Loan-loss provisioning | No documented policy triggers this (see [`110-chart-of-accounts.md`](110-chart-of-accounts.md) note on account 5004) |
| `write_off` | Loan formally written off after D+60 review | No documented process specifies exactly when/how this posts — see [`../18-credit-risk-policy/98-collections-recovery-policy.md`](../18-credit-risk-policy/98-collections-recovery-policy.md) |
| `vcn_load` | VCN funded/authorized | Tied to VCN issuance |
| `vcn_charge` | VCN actually spent at merchant checkout | Tied to checkout completion — **given checkout completion itself is an incomplete stub (`PS-BL-03`), this entry type is rarely if ever exercised in the current build** |

## What this table is useful for

Anyone building or auditing a reconciliation/financial-report process should treat this table as the checklist of "does the ledger actually record this kind of event today" — several rows above are schema-ready but functionally dormant, which is a materially different situation from "not yet designed."

## Related documents

[`109-ledger-architecture.md`](109-ledger-architecture.md), [`111-double-entry-accounting-model.md`](111-double-entry-accounting-model.md), [`117-financial-reporting.md`](117-financial-reporting.md).
