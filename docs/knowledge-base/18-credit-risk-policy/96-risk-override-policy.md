# Risk Override Policy

**Status:** STABLE (mechanism) — who is *authorized* to override, and under what documented justification standard, is thinner than the mechanism.

## What can be overridden, and by whom

| Override | Endpoint | Role | Approval gate |
|---|---|---|---|
| Credit limit adjustment | `POST /admin/credit/adjust` | `operations_manager` | Manager approval required if increase exceeds PKR 100,000 |
| Manual KYC decision (functions as an override of the automated AI approval/rejection for borderline cases) | `POST /admin/kyc/{id}/decision` | `compliance_officer` | None beyond role requirement |
| Blacklist addition | `POST /admin/risk/blacklist` | `fraud_analyst` | None documented |
| Manual credit-decision override for a `manual_review` application | (via the admin credit-application review flow) | `credit_risk_analyst` | None documented beyond role requirement |

## What every override requires (design intent)

Every override is designed to be logged: `credit_limit_history` for limit changes, `audit_trails` generally for admin actions. This is the platform's core control against unaccountable manual intervention — an override should always be traceable to a specific admin, timestamp, and (where the schema supports it) a `reason_code`.

## What's not documented — real governance gaps

- **No documented justification standard.** What counts as an acceptable reason to override an automated decline? Nothing beyond `reason_code`/`notes` free-text fields exists — no enumerated list of valid override reasons, no requirement that a reason be selected from a controlled vocabulary rather than freeform text (which makes override-reason analytics/audit harder than it needs to be).
- **No override-rate monitoring.** Given overrides bypass the automated risk controls this whole framework exists to enforce, a healthy risk practice would track override rate and outcome (do overridden approvals default at a higher rate than automated ones?) as its own metric — not currently in [`../13-analytics/42-kpi-metrics-dictionary.md`](../13-analytics/42-kpi-metrics-dictionary.md), recommend adding it.
- **Blacklist removal has no endpoint at all** (`GW-GAP-07`, also noted in [`95-fraud-investigation-workflow.md`](95-fraud-investigation-workflow.md)) — meaning the *reverse* of a blacklist override currently has no governed path.

## Related documents

[`90-credit-decision-rules.md`](90-credit-decision-rules.md), [`95-fraud-investigation-workflow.md`](95-fraud-investigation-workflow.md), [`../08-security/29-authentication-authorization.md`](../08-security/29-authentication-authorization.md) (RBAC roles).
