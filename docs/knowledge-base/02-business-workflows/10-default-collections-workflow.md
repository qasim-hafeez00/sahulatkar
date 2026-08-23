# Default / Collections Workflow

**Status:** STABLE (escalation timeline is fully specified in source docs) — automation gaps flagged inline.

## Collections Escalation Timeline

Sourced directly from `docs/System-md-files/M06-M09-payments-vcn-agent-hitl.md`:

| Day | Action | Channel |
|---|---|---|
| −7 | Pre-reminder | SMS + Push |
| −3 | Reminder | SMS + Email + Push |
| −1 | Final reminder | SMS + WhatsApp + Push |
| 0 | Due-date auto-debit attempt | JazzCash/EasyPaisa API |
| +1 | Soft overdue notice | SMS + Push |
| +3 | Firm overdue notice + retry | SMS + IVR call |
| +7 | Account restriction + human call | Call + SMS + in-app banner |
| +15 | No new purchases allowed | SMS + Call + legal warning |
| +30 | Formal notice + TASDEEQ negative report | Registered mail + SMS |
| +60 | Write-off review | Legal proceedings |

## Installment state progression

`pending` → `paid` (on time or late) | `overdue` (past due_date, not yet paid) → `defaulted` (exceeds default threshold — exact day-count threshold not specified in current engineering docs, recommend Risk confirm and document) | `waived` | `rescheduled`. Loan-level: `active` → `partially_paid` → `fully_paid` | `defaulted` | `written_off` | `disputed`. Full detail: [`../03-bnpl-financing/16-financing-state-machine.md`](../03-bnpl-financing/16-financing-state-machine.md).

## Late fees and charity routing

Late fees accrue on overdue installments but **100% are routed to charity (Edhi Foundation)** via `late_fee_charity_allocations` — SahulatKar retains none of it, by Shariah design (see [`../04-shariah/17-shariah-product-structure.md`](../04-shariah/17-shariah-product-structure.md)). Late fees must not exceed Shariah-permitted bounds (late fees cannot exceed principal in Islamic finance) — **known gap:** current code does not verify this bound (`LS-BL-08`).

## Credit bureau reporting

Successful payments generate a positive TASDEEQ report; the +30 day formal-notice stage triggers a negative TASDEEQ report. TASDEEQ reporting is described in engineering docs as mandatory (see [`../11-compliance/36-compliance-requirements-matrix.md`](../11-compliance/36-compliance-requirements-matrix.md)).

## Known automation gaps (from `docs/PRODUCTION_GAPS_REPORT.md`)

The escalation *policy* above is fully specified, but several of the automated triggers that should execute it are not yet wired:

1. **No automated charge on due date.** `BillingSweepWorker` detects due/overdue installments and accrues late fees but has no call path to actually initiate a charge via Payment Orchestrator (`LS-CRIT-04`). Installment payment today is customer-initiated only.
2. **No overdue notification event.** The `billing.installment_overdue` event that Notification Service expects is never published by any service (`NS-BL-05`) — customers who miss a payment currently receive no automated notice past the pre-due-date reminders (D-3, D-1).
3. **Charity disbursement is a stub.** `TasdeeqService.process_charity_allocation()` accrues the charity obligation but does not actually disburse funds or post the corresponding GL entry (`LS-CRIT-03`) — a Shariah-compliance-relevant gap, not just an accounting one.
4. **No escalation after 3 failed attempts.** Payment Orchestrator tracks `attempt_count` but does not escalate to HITL or trigger credit-bureau reporting after repeated failures.

## Write-off

`+60 days`: "Write-off review → Legal proceedings" per the escalation table. No detailed write-off policy (accounting treatment, loss-provisioning trigger, legal process specifics) exists in current engineering documentation beyond this one line — **recommend Finance/Legal author a dedicated write-off policy**, since this table only covers the collections *trigger*, not the accounting or legal *procedure*.

## Related documents

[`08-payment-workflow.md`](08-payment-workflow.md), [`../03-bnpl-financing/16-financing-state-machine.md`](../03-bnpl-financing/16-financing-state-machine.md), [`../11-compliance/36-compliance-requirements-matrix.md`](../11-compliance/36-compliance-requirements-matrix.md).
