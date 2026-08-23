# Credit Decision Rules

**Status:** STABLE — consolidates the decision thresholds already specified across [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md) into a single decision-rule reference, since "what exactly makes a decision approve vs. decline vs. review" is a question support/risk staff need answered in one place without reading the full layer pipeline.

## Decision outcomes

| Outcome | Triggered by |
|---|---|
| **Instant decline** | Any Layer 1 hard block (blacklist, overdue installment, unverified KYC, inactive account, prohibited product, blocked/expired CNIC, under 18, non-Pakistan delivery, emulator, new-account VPN) |
| **Decline (velocity)** | Any Layer 2 rule with `action=DECLINE` breached (e.g., >3 orders/24h, >3 failed payments/1h, >3 KYC attempts/1h) |
| **Review (velocity)** | Any Layer 2 rule with `action=REVIEW` breached (e.g., >1 order/1h, >5 new accounts/IP/24h) |
| **Auto-approve** | Composite score ≥700 (default threshold, configurable 600–800) |
| **Manual review** | Composite score 600–699 (default range) |
| **Auto-decline (score)** | Composite score <600 (default, configurable 550–650) |
| **Decline (cross-border risk)** | Layer 6 cross-border abandonment risk score >0.70 |
| **Review (cross-border risk)** | Layer 6 score 0.50–0.70 |
| **Increased down payment (cross-border risk)** | Layer 6 score 0.25–0.50 |
| **Decline (portfolio)** | Approving this order would breach a Layer 7 portfolio concentration limit |

## Precedence

Layer 1 > Layer 2 > (Layers 3–6 combine into a composite score) > Layer 7. A hard block always wins regardless of what a strong score would otherwise indicate; portfolio controls apply last, as a final gate even after an individual application would otherwise be approved.

## Manual review resolution

A `credit_risk_analyst` reviews a manual-review application against the same explanation data the SHAP explainability endpoint would surface (`GET /credit/explain/{credit_app_id}`) and issues approve/decline manually — logged with `decided_by = 'manual_admin'` (vs. `'auto_engine'` for automated decisions), per the `credit_applications` schema.

## Override authority

See [`96-risk-override-policy.md`](96-risk-override-policy.md).

## Related documents

[`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md), [`96-risk-override-policy.md`](96-risk-override-policy.md), [`92-risk-segmentation.md`](92-risk-segmentation.md).
