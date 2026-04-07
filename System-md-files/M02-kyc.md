# M02 — KYC & NADRA Integration
 
**Phase**: 1 | **Sprints**: S02–S03 (Weeks 5–8)  
**Screens**: US-04 (CNIC Front), US-05 (CNIC Back), US-06 (Liveness), US-07 (Processing), US-08 (Credit Reveal)

---

## Purpose
CNIC OCR → NADRA Verisys verification → liveness detection → face match → manual review queue → credit scoring trigger. Target: < 4 min Tier 1.

---

## KYC Pipeline

```
1. CNIC Front image → S3 presigned upload (backend never handles raw bytes)
2. OCR extract: name, CNIC number, DOB, expiry
3. CNIC Back image → S3 → MRZ extraction
4. NADRA Verisys API call → confirm valid/blocked/expired + name match
5. Selfie with liveness detection (blink + head turn)
6. Anti-spoofing AI (Shufti Pro / uqudo)
7. Face match: selfie vs CNIC photo
8. Device fingerprint passive capture (FingerprintJS Pro)
9. Auto-approve if all checks pass; manual queue if borderline
10. KYC approval → trigger credit scoring
```

---

## KYC Tiers

| Tier | Trigger | Data | Target Time |
|---|---|---|---|
| Tier 1 (Standard) | All new users | CNIC OCR, NADRA, liveness, face match, device | < 4 min |
| Tier 2 (EDD) | Orders > PKR 5K OR fraud flag | Bank/wallet connection, income proof, utility bill | < 10 min |
| Manual Review | Face match 70–80% OR NADRA mismatch 10–20% | KYC Ops review | < 24hr SLA |

---

## Database Tables

```sql
user_kyc_verifications
  id, uuid, user_id
  nadra_request_id, nadra_response_code, nadra_verified_at
  nadra_raw_response JSONB        -- stored 7 years per SECP
  cnic_front_s3, cnic_back_s3, selfie_s3 VARCHAR(512)
  liveness_score DECIMAL(5,4)    -- threshold: 0.8500
  liveness_vendor VARCHAR(50)    -- 'shufti_pro','uqudo','jumio'
  liveness_passed BOOLEAN
  status VARCHAR(20) CHECK ('pending','processing','ai_approved',
                             'manual_review','approved','rejected')
  reviewed_by_admin BIGINT
  rejection_reason TEXT
  rejection_code VARCHAR(50)
  attempt_number SMALLINT DEFAULT 1

user_devices
  id, uuid, user_id
  device_fingerprint VARCHAR(255)  -- FingerprintJS Pro hash
  device_type VARCHAR(20) CHECK ('android','ios','web','unknown')
  device_model, os_version, app_version
  push_token VARCHAR(512)
  ip_address INET, city_from_ip, country_from_ip
  is_rooted BOOLEAN, is_emulator BOOLEAN  -- fraud signals
  risk_score DECIMAL(5,4)
  is_trusted BOOLEAN DEFAULT FALSE

kyc_verification_queue (manual review)
  id, user_id, kyc_id, priority (1-5)
  assigned_to BIGINT (admin_user_id)
  status, sla_deadline, created_at
```

---

## APIs

### POST /kyc/start
**Auth**: Bearer (customer)  
**Body**: `{}`  
**Response**: `{ kyc_session_id, cnic_front_upload_url, cnic_back_upload_url }` (S3 presigned)  
**Logic**: Create `user_kyc_verifications` record with status=`pending`. Generate S3 presigned PUT URLs valid 10 min.

### POST /kyc/verify-cnic
**Auth**: Bearer  
**Body**: `{ kyc_session_id, cnic_front_s3_key, cnic_back_s3_key }`  
**Response**: `{ ocr_confidence, extracted: { name, cnic_number_masked, dob, expiry }, nadra_status }`  
**Logic**:
1. Trigger Shufti Pro CNIC OCR on S3 object
2. If confidence < 85% → `{ status: 'low_confidence', retry: true }`
3. Call NADRA Verisys API with extracted CNIC
4. NADRA returns valid/blocked/expired
5. Store result in `nadra_raw_response JSONB`  
**Errors**: `422 CNIC_BLOCKED`, `422 CNIC_EXPIRED`, `422 OCR_FAILED`, `503 NADRA_UNAVAILABLE` (queue for retry)

### POST /kyc/verify-liveness
**Auth**: Bearer  
**Body**: `{ kyc_session_id }` (liveness video uploaded direct to Shufti Pro SDK)  
**Response**: `{ liveness_passed, face_match_score, kyc_status }`  
**Logic**:
1. Shufti Pro liveness check result webhook → update `liveness_score`, `liveness_passed`
2. Face match against CNIC photo → `face_match_score`
3. If face_match >= 0.80 → status=`ai_approved` → trigger credit scoring
4. If face_match 0.70–0.79 → status=`manual_review` → insert to `kyc_verification_queue`
5. If face_match < 0.70 → status=`rejected`  
**Errors**: `422 LIVENESS_FAILED`, `422 FACE_MISMATCH`

### GET /kyc/status
**Auth**: Bearer  
**Response**: `{ kyc_status, credit_limit?, credit_band?, estimated_wait_minutes? }`  
**Usage**: Frontend polls or SSE during US-07 processing screen.

### POST /admin/kyc/{id}/decision (Admin only — compliance_officer role)
**Body**: `{ decision: 'approve'|'reject', reason_code?, notes? }`  
**Logic**: Update `user_kyc_verifications.status`, update `users.kyc_status`, if approve → trigger credit scoring, log to `audit_trails`.

---

## Manual Review Criteria (auto-route to queue)

| Condition | Threshold |
|---|---|
| Face match confidence | 70–79% |
| NADRA name mismatch | 10–20% (nickname/transliteration) |
| OCR confidence | < 85% after 2 retries |
| CNIC expired | Any expiry (user must renew) |
| Document tampering detected | Any flag |
| High-risk sanctions watchlist | Any match |

---

## Rejection Codes

`kyc_photo_quality` | `cnic_expired` | `cnic_blocked` | `face_mismatch` | `liveness_failed` | `suspected_tampering` | `watchlist_match` | `duplicate_cnic`

---

## KYC States

```
NOT_STARTED
  → IN_PROGRESS (user begins KYC)
    → UPLOADING_CNIC
    → NADRA_CHECKING
    → LIVENESS_CHECKING
    → AI_APPROVED (auto-approve, triggers credit scoring)
    → PENDING_MANUAL_REVIEW (borderline → queue)
      → APPROVED (by KYC Ops)
      → REJECTED (by KYC Ops)
    → REJECTED (hard fail: emulator, blocked CNIC, < 70% face match)
APPROVED → credit scoring triggered → users.status = 'active'
REJECTED → user notified with reason, can re-apply after 30 days
```

---

## Vendor Notes

**Shufti Pro** (primary): All-in-one — CNIC OCR + NADRA cross-reference + liveness + face match. Single API call. ~$0.40–$0.80/verification. Free trial 100 verifications.

**NADRA Verisys**: Also accessible via uqudo, Jumio Pakistan. SLA < 3s. Cache verified CNICs 30-day TTL in Redis to handle Verisys downtime. Fallback to manual queue.

**Data retention**: `nadra_raw_response` JSONB stored 7 years per SECP requirement. KYC images on S3 with server-side encryption + Glacier after 1 year.
