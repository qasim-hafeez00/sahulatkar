# KYC Verification Workflow

**Status:** STABLE (design) — vendors are largely stubbed in current code, flagged below. **KYB is not applicable** to the current product (no merchant onboarding) — see [`../01-company-product/04-product-glossary.md`](../01-company-product/04-product-glossary.md).

## Pipeline

```
1. CNIC front image → S3 presigned upload (backend never handles raw bytes)
2. OCR extract: name, CNIC number, DOB, expiry
3. CNIC back image → S3 → MRZ extraction
4. NADRA Verisys API call → confirm valid/blocked/expired + name match
5. Selfie with liveness detection (blink + head turn)
6. Anti-spoofing AI (Shufti Pro / uqudo)
7. Face match: selfie vs. CNIC photo
8. Device fingerprint passive capture (FingerprintJS Pro)
9. Auto-approve if all checks pass; manual queue if borderline
10. KYC approval → triggers credit scoring
```

## Tiers

| Tier | Trigger | Data collected | Target time |
|---|---|---|---|
| Tier 1 (Standard) | All new users | CNIC OCR, NADRA, liveness, face match, device fingerprint | <4 min |
| Tier 2 (Enhanced Due Diligence) | Orders >PKR 5,000 or a fraud flag | + bank/wallet connection, income proof, utility bill | <10 min |
| Manual Review | Borderline result (see thresholds below) | KYC Ops review | <24 hr SLA |

## Manual-review routing thresholds

| Condition | Threshold |
|---|---|
| Face match confidence | 70–79% |
| NADRA name mismatch | 10–20% (nickname/transliteration tolerance) |
| OCR confidence | <85% after 2 retries |
| CNIC expired | Any expiry — user must renew, no override |
| Document tampering detected | Any flag |
| High-risk sanctions watchlist | Any match |

Below 70% face match, or any hard-fail signal (emulator, blocked CNIC), the result is an automatic reject rather than a manual-review routing.

## Rejection codes

`kyc_photo_quality`, `cnic_expired`, `cnic_blocked`, `face_mismatch`, `liveness_failed`, `suspected_tampering`, `watchlist_match`, `duplicate_cnic`. A rejected user may re-apply after 30 days.

## Data retention

`nadra_raw_response` (JSONB) retained 7 years, cited against a SECP requirement — see [`../11-compliance/36-compliance-requirements-matrix.md`](../11-compliance/36-compliance-requirements-matrix.md) for compliance-review status. KYC images stored on S3 with server-side encryption, moved to Glacier after 1 year.

## Vendor notes

- **Shufti Pro** (primary vendor referenced in design docs): all-in-one CNIC OCR + NADRA cross-reference + liveness + face match in a single API call, ~$0.40–0.80/verification.
- **NADRA Verisys:** also reachable via uqudo or Jumio Pakistan as alternate integration paths. Design intent: cache verified CNICs for 30 days in Redis to survive Verisys downtime, falling back to the manual queue if the API is unavailable.

## Known gap — vendors are currently stubs

Per `docs/PRODUCTION_GAPS_REPORT.md` Scenario C: **NADRA and Shufti Pro integrations are stubs — no actual third-party API calls are made in the current codebase.** KYC is effectively approve/reject-by-admin only via the manual HITL queue today; there is no automated identity verification running in production yet. Anyone reading this document should understand it describes the *intended* pipeline, which is not yet live end-to-end.

## Other known gaps

- **Resubmission race condition:** `POST /kyc/resubmit` does not check whether the previous attempt is still claimed-but-undecided in the manual review queue — can create an orphaned queue item (`GW-BL-09`).
- **Resubmission counter can be bypassed:** the 3-attempt cap lives on `KycVerification.attempt_count`, which resets if a user creates a new account with the same CNIC (from Scenario C in the audit).

## Related documents

[`27-security-architecture.md`](27-security-architecture.md), [`../02-business-workflows/05-customer-journey-e2e.md`](../02-business-workflows/05-customer-journey-e2e.md), [`../03-bnpl-financing/16-financing-state-machine.md`](../03-bnpl-financing/16-financing-state-machine.md).
