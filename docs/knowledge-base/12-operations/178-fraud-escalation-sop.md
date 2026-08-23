# Fraud Escalation SOP

**Status:** STABLE — the operational-procedure companion to [`../18-credit-risk-policy/95-fraud-investigation-workflow.md`](../18-credit-risk-policy/95-fraud-investigation-workflow.md).

## When an alert reaches you

`GET /admin/risk/alerts` (fraud_analyst role) shows `user_id`, `alert_type`, `severity`, `fraud_score`, `evidence`, `recommended_action`.

## Triage steps

1. Review the evidence against the recommended action — don't apply it blindly, since the underlying models (CatBoost fraud model, Isolation Forest) are unaudited for this platform's specific patterns (Credit Engine was out of scope for the 2026-04-27 code review).
2. Cross-reference with velocity-rule breaches (see [`../18-credit-risk-policy/94-fraud-detection-rules.md`](../18-credit-risk-policy/94-fraud-detection-rules.md)) if the alert doesn't already show them — a velocity breach alongside a model-flagged score is stronger evidence than either alone.
3. Decide: dismiss (false positive, no action), escalate (needs a second opinion or a different role — e.g., a KYC-adjacent flag should loop in `compliance_officer`), or confirm (blacklist).

## Blacklisting

`POST /admin/risk/blacklist` — entity type, value, reason code, severity, optional expiry.

## Known gap to work around manually

**No endpoint exists to remove a blacklist entry** (`GW-GAP-07`). If you determine a prior blacklist action was a false positive, this currently requires a direct database change — coordinate with Engineering rather than attempting this alone, and document the correction clearly (who requested it, why, evidence reviewed) given the lack of a proper audit-trailed removal mechanism.

## Serious fraud (potential financial crime)

If an alert appears to represent organized fraud (device/SIM farming pattern, coordinated multiple accounts) rather than isolated first-party fraud, escalate to whoever owns the AML/financial-crime function once one is established (see [`../11-compliance/167-fraud-financial-crime-policy.md`](../11-compliance/167-fraud-financial-crime-policy.md)) — this may warrant FMU reporting consideration, which is currently undocumented as a process.

## Related documents

[`../18-credit-risk-policy/95-fraud-investigation-workflow.md`](../18-credit-risk-policy/95-fraud-investigation-workflow.md), [`../11-compliance/167-fraud-financial-crime-policy.md`](../11-compliance/167-fraud-financial-crime-policy.md).
