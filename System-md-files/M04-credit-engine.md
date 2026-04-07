# M04 — Credit Engine & Risk Scoring

**Phase**: 1 | **Sprint**: S04 (Weeks 9–10)

---

## Purpose
7-layer credit pipeline returning credit decision in < 3 seconds. XGBoost scoring on thin-file Pakistani users using alternative data.

---

## 7-Layer Pipeline (Total SLA: < 3s)

```
Layer 1: Hard Block Rules          < 5ms   — Redis only, zero DB
Layer 2: Velocity & Fraud Rules    < 20ms  — Redis sliding windows
Layer 3: Identity & Device Score   < 50ms  — KYC signals → 0-100
Layer 4: Alternative Data          < 200ms — JazzCash API async
Layer 5: ML Credit Scoring         < 100ms — XGBoost + LightGBM
Layer 6: Order-Specific Overlay    < 30ms  — product category, merchant
Layer 7: Portfolio-Level Controls  < 10ms  — concentration limits
```

---

## Layer 1: Hard Block Rules (Instant Decline)

Any TRUE = immediate DECLINE, no further processing:
- Entity on blacklist (CNIC/phone/device/IP)
- Active installment overdue > 0 days
- KYC not verified
- Account status != 'active'
- Product in prohibited category
- CNIC blocked/expired by NADRA
- User age < 18
- Delivery address outside Pakistan
- Device is emulator (always fraud)
- VPN detected + new user (first 7 days)

---

## Layer 2: Velocity Rules (Redis Sliding Windows)

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

---

## Layer 3: Identity & Device Score (0-100)

| Signal | Weight |
|---|---|
| NADRA verified | 30 |
| NADRA OCR confidence (scaled) | 20 |
| Selfie face match score (scaled) | 20 |
| Liveness anti-spoofing | 10 |
| Trusted device (previously seen) | 5 |
| Device not emulator/rooted | 5 |
| No active VPN | 5 |
| Phone number tenure (scaled 0-365d) | 5 |

---

## Layer 5: ML Models

**Champion (90% traffic)**: XGBoost trained on Home Credit Default Risk dataset (proxy) → retrained on real data from Month 4+  
**Challenger (10%)**: LightGBM — faster, A/B comparison  
**Fraud model**: CatBoost (handles categoricals natively: province, device brand, product category)  
**Anomaly detector**: Isolation Forest (unsupervised, catches novel fraud)

**Target variable**: DPD60 (defaulted at 60 days past due)  
**Evaluation metric**: AUC-PR (NOT AUC-ROC — data is imbalanced ~1.5-5% default)  
**Class imbalance**: SMOTEENN resampling (10:1 ratio target)

---

## Credit Bands

| Band | Score | Limit | Down Payment |
|---|---|---|---|
| A | 800-1000 | PKR 25,000 | 25% |
| B | 650-799 | PKR 10,000 | 25% |
| C | 500-649 | PKR 5,000 | 30% |
| D | 350-499 | PKR 3,000 | 33% |
| F | < 350 | DECLINE | — |

**Cold-start maximums** (first order ever, regardless of band):
- Band A: PKR 8,000 max
- Band B: PKR 5,000 max
- Band C: PKR 3,000 max
- Band D: PKR 2,000 max

---

## Layer 6: Product Category Risk Multipliers

| Category | Limit Multiplier | Cross-Border Risk |
|---|---|---|
| Clothing/footwear | 1.0 | 0.20 |
| Home appliances | 1.0 | 0.15 |
| Smartphones | 0.60 | 0.85 |
| Laptops | 0.65 | 0.80 |
| Gold jewelry | 0.40 | 0.90 |
| Cameras | 0.70 | 0.75 |

**Cross-border abandonment risk factors** (Pakistan-specific):
- Age 18-30: +0.20
- Airport-adjacent address: +0.30
- Freight forwarder address: +0.50 (instant high risk)
- First order + amount > PKR 5K: +0.20
- Account age < 7 days: +0.15
- March-April or September-October: +0.10 (peak migration months)
- Product category risk: +0.00 to +0.25

**Thresholds**: < 0.25 approve | 0.25-0.50 increase down payment | 0.50-0.70 manual review | > 0.70 decline

---

## Layer 7: Portfolio Concentration Limits

| Category | Max % Portfolio |
|---|---|
| Smartphones | 25% |
| Gold jewelry | 5% |
| Any single category | 30% |
| Any single city | 40% |
| Any single merchant | 20% |
| First-order (cold-start) users | 30% |
| Band D users | 15% |

---

## Database Tables

```sql
credit_applications
  id, uuid, user_id, application_type VARCHAR(30)
    CHECK ('onboarding','limit_increase','limit_review','manual_request','periodic_review')
  requested_limit DECIMAL(14,2)
  user_data_snapshot JSONB        -- frozen at assessment time
  credit_score DECIMAL(5,2)       -- 0-100 internal composite
  bureau_score INTEGER            -- TASDEEQ/PBCL if available
  status CHECK ('pending','processing','approved','rejected','manual_review','expired')
  approved_limit DECIMAL(14,2)
  rejection_code, rejection_reason
  decided_by VARCHAR(20) CHECK ('auto_engine','manual_admin')

risk_assessments
  id, uuid, user_id, order_id, credit_app_id
  assessment_type CHECK ('onboarding','per_order','periodic_review')
  total_score, identity_score, device_score, behavioral_score
  bank_statement_score, bureau_score, velocity_score DECIMAL(5,2)
  risk_band VARCHAR(10) CHECK ('A','B','C','D','F')
  recommended_limit DECIMAL(14,2)
  down_payment_pct DECIMAL(5,2)
  flags TEXT[]                    -- 'new_device','vpn_detected','sim_swap_risk'
  explanation JSONB               -- per-factor human-readable breakdown
  model_version VARCHAR(20)
  processing_time_ms INTEGER

credit_limit_history
  id, user_id, old_limit, new_limit DECIMAL(14,2)
  reason_code, changed_by_type, changed_by_id, created_at  -- immutable

blacklisted_entities
  entity_type VARCHAR(30)         -- 'cnic','phone','email','device_fp','ip','merchant'
  entity_value VARCHAR(255)
  reason_code, severity, blacklisted_by
  expires_at, is_active BOOLEAN

fraud_rules
  rule_code, rule_name
  condition_json JSONB            -- configurable without code change
  threshold, action VARCHAR(20)   -- 'block','flag','review'
  priority, is_active BOOLEAN

velocity_checks
  user_id, device_id, ip_address INET
  check_type VARCHAR(50)
  window_start, window_end TIMESTAMP
  count INTEGER, threshold INTEGER, breached BOOLEAN
```

---

## APIs

### GET /credit/check
**Auth**: Bearer (Gateway API calls this internally)  
**Query**: `?user_id=uuid&order_amount=decimal`  
**Response**:
```json
{
  "approved": true,
  "risk_band": "B",
  "approved_limit": 10000,
  "down_payment_pct": 25,
  "rejection_reason": null,
  "processing_time_ms": 847,
  "explanation": { "top_factors": [...] }
}
```
**SLA**: < 3 seconds p99

### GET /credit/me
**Auth**: Bearer (customer)  
**Response**: `{ credit_limit, available_credit, risk_band, on_time_rate, utilization_pct }`

### POST /admin/credit/adjust (operations_manager role)
**Body**: `{ user_id, new_limit, reason_code, notes }`  
**Logic**: Requires manager approval if > PKR 100K increase. Logs to `credit_limit_history` + `audit_trails`. Notifies user.

### GET /admin/risk/alerts
**Auth**: Admin (fraud_analyst role)  
**Response**: `{ alerts: [{ user_id, alert_type, severity, fraud_score, evidence, recommended_action }] }`

### POST /admin/risk/blacklist
**Auth**: Admin (fraud_analyst role)  
**Body**: `{ entity_type, entity_value, reason_code, severity, expires_at? }`

---

## Credit Policy Parameters (Configurable in System Settings)

| Parameter | Default | Range |
|---|---|---|
| Auto-approve threshold | 700+ | 600-800 |
| Manual review range | 600-699 | derived |
| Auto-decline below | < 600 | 550-650 |
| First-time user limit | PKR 25,000 | PKR 10K-50K |
| Maximum limit (all users) | PKR 500,000 | PKR 100K-1M |
| Credit increase after N payments | 3 | 1-6 |
| Credit increase percentage | 25% | 10-50% |
| Max debt-to-income ratio | 40% | 30-50% |
| Min monthly income requirement | PKR 30,000 | PKR 20K-50K |

---

## SHAP Explainability (SECP Compliance)

Every declined or borderline decision generates a SHAP explanation:
- Top 5 positive/negative factors
- Human-readable labels (not technical feature names)
- `regulation_ref: "SECP NBFC Circular 15/2022"`
- Available via `GET /credit/explain/{credit_app_id}`
