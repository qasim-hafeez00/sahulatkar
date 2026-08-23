# Fraud Detection Workflow

**Status:** STABLE — the workflow-format view of the Credit Engine's fraud-relevant layers (1, 2, and the CatBoost fraud model within Layer 5), which remain fully specified in [`../18-credit-risk-policy/`](../18-credit-risk-policy/) and [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md).

## Trigger

Every credit check (i.e., every order), plus continuous passive signal collection (device fingerprinting, velocity counters) from the moment of registration onward.

## Actors

Credit Engine (automated detection), fraud_analyst (manual investigation/blacklisting).

## Steps

1. **Real-time, automated (every order):** Layer 1 hard blocks (instant decline on blacklist match, emulator, new-account VPN, etc.) and Layer 2 velocity rules (order/KYC/promo abuse windows) run before any other scoring — see [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md).
2. **Model-based (part of Layer 5):** the CatBoost fraud model and Isolation Forest anomaly detector run alongside the credit-scoring XGBoost/LightGBM ensemble, flagging orders for review even when the credit score alone would approve.
3. **Manual investigation:** flagged users/orders surface on `GET /admin/risk/alerts` (fraud_analyst role) with evidence and a recommended action.
4. **Blacklisting:** confirmed fraud results in a `POST /admin/risk/blacklist` entry (CNIC/phone/device/IP/merchant), which feeds back into Layer 1 for all future checks.

## Business rules

Full detail: [`../18-credit-risk-policy/`](../18-credit-risk-policy/) (fraud risk framework, fraud detection rules, fraud investigation workflow — see those documents for the deeper policy layer this workflow triggers into).

## System services involved

Credit Engine (detection + scoring), Gateway (surfaces alerts to admin).

## Known gap

**No endpoint exists to remove a blacklist entry** (`GW-GAP-07`) — only to add one. This means a false-positive fraud flag currently has no self-service or even admin-UI-driven correction path; removal would require a direct database change, which is an operational risk (both for customers wrongly blocked and for the audit trail of who removed what and why).

## Expected outcome

Either the order proceeds normally (no fraud signal), is declined/reviewed at the credit-decision stage (see [`51-credit-eligibility-workflow.md`](51-credit-eligibility-workflow.md)), or results in a blacklist action for confirmed fraud.

## Related documents

[`../18-credit-risk-policy/`](../18-credit-risk-policy/), [`51-credit-eligibility-workflow.md`](51-credit-eligibility-workflow.md), [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md).
