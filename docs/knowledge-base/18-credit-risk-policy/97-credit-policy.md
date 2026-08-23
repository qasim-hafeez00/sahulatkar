# Credit Policy

**Status:** STABLE — the consolidated policy-parameter reference, pulling together every configurable credit-policy value scattered across the eligibility/limit documents into one table, since a Risk/Compliance reader typically needs "what are our current settings" in one place.

## Current policy parameters

| Parameter | Default | Configurable range |
|---|---|---|
| Auto-approve score threshold | 700+ | 600–800 |
| Manual review score range | 600–699 | derived |
| Auto-decline score threshold | <600 | 550–650 |
| First-time user limit | PKR 25,000 | PKR 10K–50K |
| Maximum limit (all users) | PKR 500,000 | PKR 100K–1M |
| Credit increase trigger (consecutive on-time payments) | 3 | 1–6 |
| Credit increase percentage | 25% | 10–50% |
| Max debt-to-income ratio | 40% | 30–50% |
| Min monthly income requirement | PKR 30,000 | PKR 20K–50K |
| Cross-border risk decline threshold | 0.70 | not stated as configurable |
| Cross-border risk manual-review threshold | 0.50–0.70 | not stated as configurable |

## Governance status — this is the load-bearing caveat

**None of these parameters are actually admin-configurable in the current build.** `GET/PUT /api/v1/admin/system/parameters` (the intended mechanism) is a stub (`GW-GAP-01`, `GW-GAP-02`) — meaning every value in the table above is effectively hardcoded in application code today, despite being documented as "configurable." Any change requires a code deploy, not a policy-console update. **This is the single most consequential gap in this document**: a credit policy that can't actually be adjusted without engineering involvement isn't really a policy lever Risk controls day to day.

## Who owns policy changes (proposed, not formally assigned in current docs)

`credit_risk_analyst`/Risk leadership should own the values in this table; changes should go through the same kind of review/sign-off a responsible-lending function would apply (see [`../11-compliance/38-responsible-financing-policy.md`](../11-compliance/38-responsible-financing-policy.md)) rather than being adjusted ad hoc by whichever engineer touches the relevant code.

## Related documents

[`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md), [`../03-bnpl-financing/15-credit-limit-rules.md`](../03-bnpl-financing/15-credit-limit-rules.md), [`../11-compliance/38-responsible-financing-policy.md`](../11-compliance/38-responsible-financing-policy.md).
