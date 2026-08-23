# Credit Limit Rules

**Status:** STABLE — sourced from `docs/System-md-files/M04-credit-engine.md` and the platform quick-reference.

## Credit bands

| Band | Score | Limit | Down payment |
|---|---|---|---|
| A | 800–1000 | PKR 25,000 | 25% |
| B | 650–799 | PKR 10,000 | 25% |
| C | 500–649 | PKR 5,000 | 30% |
| D | 350–499 | PKR 3,000 | 33% |
| F | <350 | Decline | — |

## Cold-start limits (first order ever, regardless of band)

| Band | Cold-start max |
|---|---|
| A | PKR 8,000 |
| B | PKR 5,000 |
| C | PKR 3,000 |
| D | PKR 2,000 |

The platform quick-reference also cites a general cold-start range of **PKR 3,000 → PKR 100,000** as the limit growth path from first order to a fully seasoned user — the table above governs the very first order specifically; growth beyond that follows the limit-increase rule below.

## Initial limit

Set at KYC approval / first credit assessment, band-determined per the table above, capped by the cold-start maximum on the first order.

## Limit increase

Per configurable policy parameters (see [`14-eligibility-rules.md`](14-eligibility-rules.md)): triggered after N on-time payments (default 3, range 1–6), increase percentage default 25% (range 10–50%). Increases above PKR 100,000 require manager approval (`POST /admin/credit/adjust`, logged to `credit_limit_history` and `audit_trails`, customer notified).

## Limit decrease

Not explicitly speced as an automated rule in current engineering docs beyond the general admin override capability (`POST /admin/credit/adjust`) and the fact that Layer 1 hard-blocks (overdue installment, blacklist, etc.) effectively zero out *available* limit without changing the underlying *approved* limit. Recommend Risk define an explicit automated limit-decrease trigger (e.g., on missed payment, on negative TASDEEQ signal) if one is intended — none is documented today.

## Limit expiry

Not specified in current engineering docs — no TTL or periodic-review expiry is defined on `credit_applications`/`risk_assessments` beyond the `application_type = 'periodic_review'` category existing as a concept. Recommend Risk confirm whether limits should auto-expire or require periodic re-verification.

## Limit utilization / available limit

`available_credit = credit_limit − outstanding principal across active loans`. **Known gap (GW-BL-01, critical):** `available_credit` is not currently decremented when an order is initiated — only credit-checked. Two concurrent orders from the same user can each pass the eligibility check against the full limit, allowing a user to exceed their approved limit before either order completes. This is a Priority-1 (launch-blocking) fix.

Separately, `GET /credit/status` reads `user.credit_limit` from the ORM session without an explicit refresh after a credit-engine update, so a user may see a stale limit shortly after a change (`GW-BL-07`, lower severity).

## Portfolio concentration limits governing aggregate limit exposure

See Layer 7 in [`14-eligibility-rules.md`](14-eligibility-rules.md) — these cap exposure by category/city/merchant/segment at the portfolio level, independent of any single user's limit.

## Related documents

[`14-eligibility-rules.md`](14-eligibility-rules.md), [`16-financing-state-machine.md`](16-financing-state-machine.md), [`../02-business-workflows/10-default-collections-workflow.md`](../02-business-workflows/10-default-collections-workflow.md).
