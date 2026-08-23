# Fraud Risk Framework

**Status:** STABLE (mechanism) — policy-level fraud-loss appetite is undocumented, same gap pattern as credit risk generally.

## Fraud detection layers (mechanism, fully specified elsewhere)

Layer 1 hard blocks (blacklist, emulator, new-account VPN), Layer 2 velocity rules, and the CatBoost fraud model + Isolation Forest anomaly detector within Layer 5 — see [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md) for full detail. This document covers the framework-level policy questions those mechanisms serve, not the mechanisms themselves.

## Fraud typologies the current design appears to target

| Typology | Mitigated by |
|---|---|
| Synthetic/stolen identity | NADRA verification, liveness/face-match, device fingerprinting |
| Account takeover | Single concurrent session, MFA on admin, device trust scoring |
| First-party ("never-pay") fraud | Cold-start caps, velocity limits, credit scoring on thin-file signals |
| Bust-out fraud (build trust, then max out and default) | Layer 7 portfolio controls, limit-increase pacing (3 on-time payments minimum before increase) |
| Device/SIM farming | `cnic_per_device` velocity rule (max 2 CNICs per device per 7 days) |
| Promo/referral abuse | `promo_per_user` velocity rule |

## What's not covered by the current design (gaps, not just undocumented policy)

- **Merchant-side fraud** (a third-party site itself being fraudulent, non-delivering, or a scam) — the platform's risk framework is entirely customer-side; there's no documented merchant-fraud detection given the vendor-agnostic model has no merchant vetting at all (see [`../17-merchant-documentation/68-merchant-verification-kyb.md`](../17-merchant-documentation/68-merchant-verification-kyb.md)).
- **Collusion/friendly fraud** (a genuine customer disputing a legitimate charge, or colluding with a merchant on a fake return) — not addressed anywhere, connects to the undocumented chargeback workflow ([`../02-business-workflows/54-chargeback-dispute-workflow.md`](../02-business-workflows/54-chargeback-dispute-workflow.md)).
- **No documented fraud-loss appetite or target rate**, unlike the vague credit-loss break-even figure — the admin dashboard's "fraud loss rate" traffic-light thresholds (green <0.2%, red >0.3%, see [`../13-analytics/42-kpi-metrics-dictionary.md`](../13-analytics/42-kpi-metrics-dictionary.md)) are the closest thing to a target, but no document explains how those specific thresholds were derived.

## Related documents

[`94-fraud-detection-rules.md`](94-fraud-detection-rules.md), [`95-fraud-investigation-workflow.md`](95-fraud-investigation-workflow.md), [`../02-business-workflows/58-fraud-detection-workflow.md`](../02-business-workflows/58-fraud-detection-workflow.md).
