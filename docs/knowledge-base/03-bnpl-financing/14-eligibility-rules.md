# Eligibility Rules

**Status:** STABLE — sourced from `docs/System-md-files/M04-credit-engine.md`.

Eligibility is decided by the 7-layer credit engine pipeline, target SLA under 3 seconds end-to-end.

## Layer 1 — Hard Block Rules (<5ms, Redis only, zero DB)

Any one of the following is an instant decline, no further processing:

- Entity (CNIC/phone/device/IP) on blacklist
- Any active installment overdue
- KYC not verified
- Account status ≠ `active`
- Product in a prohibited category
- CNIC blocked or expired (per NADRA)
- User under 18
- Delivery address outside Pakistan
- Device is an emulator (always treated as fraud)
- VPN detected on a new account (first 7 days)

## Layer 2 — Velocity & Fraud Rules (<20ms, Redis sliding windows)

| Rule | Entity | Window | Threshold | Action |
|---|---|---|---|---|
| orders_per_24h | user | 24h | 3 | DECLINE |
| orders_per_1h | user | 1h | 1 | REVIEW |
| failed_payments_1h | user | 1h | 3 | DECLINE |
| new_accounts_per_ip | IP | 24h | 5 | REVIEW |
| orders_per_device | device fingerprint | 24h | 3 | REVIEW |
| kyc_attempts | phone | 1h | 3 | DECLINE |
| cnic_per_device | device fingerprint | 7d | 2 | DECLINE |
| promo_per_user | user | 24h | 2 | DECLINE |

## Layer 3 — Identity & Device Score (<50ms, 0–100 scale)

| Signal | Weight |
|---|---|
| NADRA verified | 30 |
| NADRA OCR confidence (scaled) | 20 |
| Selfie face-match score (scaled) | 20 |
| Liveness anti-spoofing | 10 |
| Trusted device (previously seen) | 5 |
| Device not emulator/rooted | 5 |
| No active VPN | 5 |
| Phone number tenure (scaled 0–365d) | 5 |

## Layer 4 — Alternative Data (<200ms)

JazzCash API and device-signal based alternative underwriting data — used specifically because most applicants are thin-file with no bureau history.

## Layer 5 — ML Credit Scoring (<100ms)

- **Champion (90% of traffic):** XGBoost, trained on Home Credit Default Risk dataset as a proxy pending real portfolio data from Month 4+.
- **Challenger (10%):** LightGBM, A/B compared against champion.
- **Fraud model:** CatBoost (handles categorical features like province/device brand/product category natively).
- **Anomaly detector:** Isolation Forest (unsupervised, catches novel fraud patterns).
- **Target variable:** DPD60 (defaulted at 60 days past due). **Metric:** AUC-PR, not AUC-ROC, because the dataset is imbalanced (~1.5–5% default rate). **Class imbalance handling:** SMOTEENN resampling to a 10:1 target ratio.

## Layer 6 — Order-Specific Overlay (<30ms)

Product category risk multipliers and Pakistan-specific cross-border abandonment risk:

| Category | Limit multiplier | Cross-border risk |
|---|---|---|
| Clothing/footwear | 1.0 | 0.20 |
| Home appliances | 1.0 | 0.15 |
| Smartphones | 0.60 | 0.85 |
| Laptops | 0.65 | 0.80 |
| Gold jewelry | 0.40 | 0.90 |
| Cameras | 0.70 | 0.75 |

Cross-border abandonment risk factors (additive): age 18–30 (+0.20), airport-adjacent address (+0.30), freight-forwarder address (+0.50, instant high risk), first order + amount > PKR 5,000 (+0.20), account age < 7 days (+0.15), March–April or September–October / peak migration months (+0.10), plus the product category's own risk contribution. Thresholds: <0.25 approve, 0.25–0.50 increase down payment, 0.50–0.70 manual review, >0.70 decline.

## Layer 7 — Portfolio-Level Controls (<10ms)

| Category | Max % of portfolio |
|---|---|
| Smartphones | 25% |
| Gold jewelry | 5% |
| Any single category | 30% |
| Any single city | 40% |
| Any single merchant | 20% |
| First-order (cold-start) users | 30% |
| Band D users | 15% |

## Configurable policy parameters

| Parameter | Default | Range |
|---|---|---|
| Auto-approve threshold | 700+ | 600–800 |
| Manual review range | 600–699 | derived |
| Auto-decline below | <600 | 550–650 |
| First-time user limit | PKR 25,000 | PKR 10K–50K |
| Maximum limit (all users) | PKR 500,000 | PKR 100K–1M |
| Max debt-to-income ratio | 40% | 30–50% |
| Min monthly income requirement | PKR 30,000 | PKR 20K–50K |

**Known gap:** `GET /api/v1/admin/system/parameters` (the endpoint meant to make these configurable without a code deploy) is a stub as of the last audit — these values are effectively hardcoded today (`GW-GAP-01`).

## Explainability (SECP compliance intent)

Every declined or borderline decision is designed to generate a SHAP explanation (top 5 positive/negative factors, human-readable, tagged `regulation_ref: "SECP NBFC Circular 15/2022"`), available via `GET /credit/explain/{credit_app_id}`. Whether "SECP NBFC Circular 15/2022" is confirmed applicable to SahulatKar's actual licensing category is a legal question — see [`../11-compliance/36-compliance-requirements-matrix.md`](../11-compliance/36-compliance-requirements-matrix.md).

## Related documents

[`15-credit-limit-rules.md`](15-credit-limit-rules.md), [`../05-architecture/microservices/credit-engine.md`](../05-architecture/microservices/credit-engine.md), [`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md).
