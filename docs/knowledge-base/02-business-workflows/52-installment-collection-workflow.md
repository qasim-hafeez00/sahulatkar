# Installment Collection Workflow

**Status:** STABLE — the recurring-collection slice pulled out from [`08-payment-workflow.md`](08-payment-workflow.md) as its own document, since it's the platform's core recurring operational job (runs daily, at scale, for the life of every active loan).

## Trigger

Daily billing sweep (`pg_cron`, 08:00) via Ledger Service's `BillingSweepWorker`.

## Actors

Ledger Service (detection), Payment Orchestrator (should execute the charge — see gap below), Notification Service (reminders), customer.

## Preconditions

At least one `installments` row with `status='pending'` and `due_date <= CURRENT_DATE`.

## Steps (target design)

1. Sweep queries `installments WHERE status='pending' AND due_date <= CURRENT_DATE` via the critical partial index.
2. Pre-due reminders already sent at D-7, D-3, D-1 (SMS/email/push/WhatsApp per the escalation timeline).
3. On due date, an auto-debit attempt fires against JazzCash/EasyPaisa (or Raast once live).
4. On success: installment marked `paid`, journal entry created, positive TASDEEQ report.
5. On failure: retry per the schedule (same day 6PM, next day 9AM, day+2 12PM), then flagged for manual collections outreach.

## Business rules

Full retry schedule and collections escalation timeline: [`10-default-collections-workflow.md`](10-default-collections-workflow.md). Late fees, once accrued, are 100% charity-routed — never platform revenue.

## System services involved

Ledger Service (detection + accrual), Payment Orchestrator (execution — see gap), Notification Service (reminders + overdue notice — partially gapped).

## Events generated (target)

None currently published on successful auto-collection beyond the general `payment.confirmed` event Payment Orchestrator would emit if it executed the charge.

## Database changes

`installments` (status, `paid_amount`, `paid_at`, `late_fee_amount`), `journal_entries`/`journal_entry_lines` (on success).

## Known gap — this workflow is not actually automatic today

**Critical (`LS-CRIT-04`):** the billing sweep correctly identifies due/overdue installments and accrues late fees, but has **no implemented call path into Payment Orchestrator to actually attempt the charge.** As of the last audit, installment payment is customer-initiated only (`POST /api/v1/payments/installment/{id}/pay`). This workflow document describes the intended automatic design — the "Steps" section above should be read as target behavior, not confirmed current behavior, until `POST /api/internal/installments/{id}/auto-collect` (`PO-EP-06`) is implemented.

## Expected outcome

Installment reaches `paid` status without requiring the customer to take manual action.

## Related documents

[`08-payment-workflow.md`](08-payment-workflow.md), [`10-default-collections-workflow.md`](10-default-collections-workflow.md), [`53-missed-payment-workflow.md`](53-missed-payment-workflow.md).
