# Account Suspension SOP

**Status:** STABLE — operational procedure companion to [`../02-business-workflows/59-account-suspension-workflow.md`](../02-business-workflows/59-account-suspension-workflow.md).

## When to suspend manually (vs. automated triggers)

Automated: entering the +7-day collections escalation stage, a confirmed fraud/blacklist action. Manual (`operations_manager` discretion): a case-specific concern not covered by the automated triggers — e.g., a suspicious pattern that doesn't yet meet a formal fraud-blacklist threshold but warrants a precautionary hold pending investigation.

## Before manually suspending

Document the specific reason clearly (free-text `notes` field, since no controlled reason-code vocabulary currently exists for overrides generally — see [`../18-credit-risk-policy/96-risk-override-policy.md`](../18-credit-risk-policy/96-risk-override-policy.md)) — this matters because there's no automated audit specifically for manual suspensions distinct from the general `audit_trails` mechanism, so a clear note is the practical safeguard until better tooling exists.

## What a suspension does and doesn't do

Blocks new orders (Layer 1 hard block on `account status != 'active'`). Does **not** affect existing loan obligations — a suspended customer's installments continue on schedule. Make sure the customer understands this distinction when informing them of a suspension, since "suspended" could otherwise be misread as "your obligations are paused too."

## Related documents

[`../02-business-workflows/59-account-suspension-workflow.md`](../02-business-workflows/59-account-suspension-workflow.md), [`180-account-recovery-sop.md`](180-account-recovery-sop.md).
