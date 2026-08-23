# Credit Limit Algorithm

**Status:** STABLE — the algorithmic view of [`../03-bnpl-financing/15-credit-limit-rules.md`](../03-bnpl-financing/15-credit-limit-rules.md), written as a step-by-step procedure rather than a rules table.

## Algorithm (first-time applicant)

```
1. Compute composite risk score (Layers 3–6 of the eligibility engine)
2. Map score to a band: A (800-1000) / B (650-799) / C (500-649) / D (350-499) / F (<350, decline)
3. Assign the band's nominal limit: A=25,000 / B=10,000 / C=5,000 / D=3,000 PKR
4. Cap at the band's cold-start maximum for a first order:
   A→8,000 / B→5,000 / C→3,000 / D→2,000 PKR
5. Assign down_payment_pct per band: A/B=25% / C=30% / D=33%
6. Apply Layer 6 order-specific adjustment (category multiplier, cross-border risk)
7. Apply Layer 7 portfolio check — reject/reduce if a concentration limit would be breached
8. Final approved_limit = min(step 4 result, step 6-adjusted amount, requested order amount)
```

## Algorithm (returning applicant, limit increase)

```
1. Count consecutive on-time payments since last limit change
2. If count >= threshold (default 3, configurable 1-6):
     new_limit = current_limit × (1 + increase_pct)   [default 25%, configurable 10-50%]
3. If new_limit > 100,000 PKR: require manager approval before applying
4. Log to credit_limit_history (immutable), notify customer
```

## Known implementation gap affecting both algorithms

`available_credit` (the figure that should reflect true remaining capacity) is not decremented at order initiation (`GW-BL-01`) — meaning step 8 of the first-time algorithm and any subsequent order's eligibility check against a returning customer's utilization are both evaluated against a **stale/incorrect available-credit figure** until this is fixed. This is the single most consequential bug in the credit-limit algorithm's actual (vs. designed) behavior.

## What's not algorithmically specified

Limit *decrease* has no documented automated trigger (see [`../03-bnpl-financing/15-credit-limit-rules.md`](../03-bnpl-financing/15-credit-limit-rules.md)) — the algorithm above only covers increase. Recommend Risk define a symmetric decrease algorithm (e.g., triggered by a missed payment, a negative TASDEEQ signal, or a portfolio-level risk tightening decision).

## Related documents

[`../03-bnpl-financing/15-credit-limit-rules.md`](../03-bnpl-financing/15-credit-limit-rules.md), [`90-credit-decision-rules.md`](90-credit-decision-rules.md).
