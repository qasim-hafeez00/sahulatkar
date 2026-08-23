# Missed Payment Workflow

**Status:** STABLE — the specific "what happens starting the moment a payment is missed" slice of [`10-default-collections-workflow.md`](10-default-collections-workflow.md), separated out because it's a distinct trigger point support/collections staff need to reason about on its own.

## Trigger

An installment's due date passes with `status` still `pending` (i.e., the day-0 auto-debit attempt, and its same-day retry, both failed or never fired).

## Actors

Ledger Service, Payment Orchestrator, Notification Service, collections staff (from day +7 onward), customer.

## Preconditions

A due installment with no successful payment recorded.

## Steps

1. `installments.status` transitions from `pending` → `overdue`, `days_overdue` begins incrementing.
2. Retry attempts continue per the schedule (next day 9AM, day+2 12PM).
3. +1 day: soft overdue notice (SMS + push).
4. +3 days: firm overdue notice + retry (SMS + IVR call).
5. +7 days: account restriction (no new purchases) + human call.
6. +15 days: legal warning notice.
7. +30 days: formal notice + negative TASDEEQ report.
8. +60 days: write-off review begins.

## Business rules

Late fee accrues on the overdue installment but is 100% charity-routed on eventual payment — never platform revenue. Late fees must not exceed the Shariah-permitted bound relative to principal (currently unverified in code — `LS-BL-08`).

## System services involved

Ledger Service (detects overdue, accrues late fee), Notification Service (should fire overdue notifications — currently gapped), Payment Orchestrator (should retry charges — currently gapped for auto-collection specifically).

## Events generated

`billing.installment_overdue` **should** be published by Ledger Service — **confirmed not implemented** (`NS-BL-05`), meaning Notification Service never learns an installment went overdue and cannot fire the SMS/call escalation steps above automatically.

## Database changes

`installments.status`, `days_overdue`, `late_fee_amount`, `retry_count`.

## Failure cases

Customer disputes the missed payment (claims they paid) → requires manual reconciliation against `payment_transactions`, no dedicated dispute workflow currently exists for this specific scenario beyond general support escalation.

## Expected outcome

Either the installment is eventually collected (loan returns to `active`/`partially_paid`) or the loan proceeds toward `defaulted`/`written_off` per [`10-default-collections-workflow.md`](10-default-collections-workflow.md).

## Related documents

[`10-default-collections-workflow.md`](10-default-collections-workflow.md), [`52-installment-collection-workflow.md`](52-installment-collection-workflow.md), [`../12-operations/`](../12-operations/) SOPs.
