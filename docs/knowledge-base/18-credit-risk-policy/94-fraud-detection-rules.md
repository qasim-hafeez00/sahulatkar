# Fraud Detection Rules

**Status:** STABLE — the specific, enumerable rules (as opposed to the framework/typology discussion in [`93-fraud-risk-framework.md`](93-fraud-risk-framework.md)).

## Velocity rules (Layer 2 — the platform's primary configurable fraud-rule set)

| Rule code (inferred naming) | Entity | Window | Threshold | Action |
|---|---|---|---|---|
| orders_per_24h | user | 24h | 3 | DECLINE |
| orders_per_1h | user | 1h | 1 | REVIEW |
| failed_payments_1h | user | 1h | 3 | DECLINE |
| new_accounts_per_ip | IP | 24h | 5 | REVIEW |
| orders_per_device | device fingerprint | 24h | 3 | REVIEW |
| kyc_attempts | phone | 1h | 3 | DECLINE |
| cnic_per_device | device fingerprint | 7d | 2 | DECLINE |
| promo_per_user | user | 24h | 2 | DECLINE |

## Configurable rule engine

`fraud_rules` table stores rules as `condition_json` (JSONB) with a `threshold` and `action`, explicitly designed to be editable without a code deploy (see [`../07-database/26-database-dictionary.md`](../07-database/26-database-dictionary.md)) — the table above represents the seed/default rule set, not a hardcoded final list. New rules should be added here as they're identified, via this configurable mechanism, not by hardcoding new logic into the Credit Engine.

## Device-level fraud signals (feed Layer 3 identity/device scoring, not standalone rules)

`is_rooted`, `is_emulator` (emulator = automatic fraud, per Layer 1), VPN detection (new-account VPN = automatic fraud, per Layer 1; established-account VPN is scored, not blocked), IP geolocation vs. claimed address mismatch.

## Rule-tuning guidance (not documented — proposed for Risk/Fraud team)

No documented process exists for how these thresholds were originally set or how they should be revised as real fraud/false-positive data accumulates. Recommend the Fraud team establish a regular (e.g., monthly) rule-tuning review using actual `fraud_rules` hit-rate and outcome data, since these thresholds are exactly the kind of parameter that needs to evolve with observed behavior rather than stay fixed at launch-time estimates.

## Related documents

[`93-fraud-risk-framework.md`](93-fraud-risk-framework.md), [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md).
