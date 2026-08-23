# Account Recovery SOP

**Status:** STABLE — operational procedure companion to [`../02-business-workflows/60-account-recovery-workflow.md`](../02-business-workflows/60-account-recovery-workflow.md).

## Payment-triggered recovery

Should be automatic once the triggering overdue installment is paid — **but confirm this actually happened** rather than assuming it, since the automatic status flip from `suspended` back to `active` is not confirmed as tested/verified behavior (per the gap noted in [`../02-business-workflows/60-account-recovery-workflow.md`](../02-business-workflows/60-account-recovery-workflow.md)). If a customer reports they paid but still can't order, manually verify `users.status` and correct it if needed.

## Appeal-based recovery (fraud/manual suspension)

No formal appeal process exists yet (see [`../02-business-workflows/60-account-recovery-workflow.md`](../02-business-workflows/60-account-recovery-workflow.md)). Interim practice: the customer's request routes through whatever general support channel currently exists; the reviewing staff member (fraud_analyst for a fraud-related suspension, operations_manager for other cases) should re-examine the original evidence and either lift the suspension or explain why it stands. Document the outcome clearly given the lack of formal tooling for this.

## What "burden of proof" should look like (proposed, not formal policy)

A payment-related suspension should require minimal friction to lift (the payment itself is the proof). A fraud-related suspension should require genuine re-investigation before lifting — don't treat a customer's assertion alone as sufficient to reverse a fraud-confirmed blacklist action; that decision should go through the same rigor as the original confirmation, not a lighter-touch appeal shortcut.

## Related documents

[`../02-business-workflows/60-account-recovery-workflow.md`](../02-business-workflows/60-account-recovery-workflow.md), [`179-account-suspension-sop.md`](179-account-suspension-sop.md).
