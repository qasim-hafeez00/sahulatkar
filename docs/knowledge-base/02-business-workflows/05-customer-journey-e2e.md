# End-to-End Customer Journey

**Status:** STABLE (target design) — deviations from current code noted inline with gap IDs from `docs/PRODUCTION_GAPS_REPORT.md`.

## Journey Map

```
Discover
  ↓
Register (phone OTP)
  ↓
KYC (CNIC OCR → NADRA → liveness → face match)
  ↓
Paste product URL
  ↓
AI extraction (Universal Product Object)
  ↓
Credit assessment (<3s)
  ↓
Financing offer presented
  ↓
Sign Wakalah Agreement (OTP)
  ↓
Sign Murabaha Contract (OTP)          ← HARD GATE
  ↓
Pay down payment
  ↓
VCN issued
  ↓
AI agent completes checkout at merchant
  ↓
Delivery tracked
  ↓
Biweekly installments
  ↓
Loan completed
```

## Stage-by-stage detail

### 1. Registration
`POST /auth/register/initiate` → phone OTP via Jazz SMS → `POST /auth/verify-otp` issues JWT (15-min access / 24-hr refresh). Account status starts `pending_kyc`. Full API detail: [`../08-security/29-authentication-authorization.md`](../08-security/29-authentication-authorization.md).

### 2. KYC
CNIC front/back upload (S3 presigned, backend never touches raw image bytes) → OCR → NADRA Verisys check → liveness selfie → face match. Auto-approved if face match ≥80%, routed to a 24-hour-SLA manual review queue if 70–79%, hard-rejected below 70% or on NADRA/document red flags. Target: <4 minutes for Tier 1. Full detail: [`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md).

### 3. Paste product URL
Customer pastes any product URL. Backend normalizes it (strips tracking params, expands shortlinks), classifies the platform, checks the prohibited-category list, then runs the extraction waterfall (Rye API → JSON-LD → Playwright+LLM → HITL) to produce a Universal Product Object (UPO). **Known gap (PS-BUG-01/02):** as of the last audit, the scraping worker crashes on every job due to an undefined variable, and the prohibited-category check is not actually wired into the worker's save path — both are Priority-1 blockers.

### 4. Credit assessment
The 7-layer credit engine returns approve/decline, risk band, limit, and down-payment percentage in under 3 seconds. Full detail: [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md).

### 5. Offer
Customer sees cost price + disclosed markup + down payment + full installment schedule, for each available plan (pay-in-3/4/6). **Known gap (PS-GAP-02):** the tiered markup used to generate this offer has not yet received Shariah board sign-off.

### 6–7. Contract signing (HARD GATE)
Wakalah signed first (authorizes the purchase), then Murabaha (fixes the sale price, profit, and installment schedule). Both via OTP + explicit confirmation checkbox on the Murabaha. Order status only reaches `contracts_signed` — the only state that permits VCN issuance — after Murabaha signing. Full detail: [`../03-bnpl-financing/16-financing-state-machine.md`](../03-bnpl-financing/16-financing-state-machine.md), [`../04-shariah/17-shariah-product-structure.md`](../04-shariah/17-shariah-product-structure.md). **Known gap (GW-BL-03):** code does not currently enforce that Wakalah must be signed before Murabaha can be generated.

### 8. Down payment
25–40% of order value via Safepay, JazzCash, or EasyPaisa. Confirmed via webhook → publishes `payment.down_payment_confirmed`. Full detail: [`08-payment-workflow.md`](08-payment-workflow.md).

### 9. VCN issuance
Single-use, MCC-locked, amount-capped virtual card issued only once `contracts_signed` + payment confirmed. **Known gap (PO-CRIT-04):** expired VCNs are marked expired locally but not actually voided on the issuer side, leaving the card live for up to 24 extra hours.

### 10. Checkout execution
Playwright agent (with residential proxy, stealth patches, VLM self-healing) completes checkout using the VCN. HITL escalation (15-min SLA) for CAPTCHAs, bot detection, 3DS, or repeated failure. **Known gap (PS-BL-03) — the most severe in the current codebase:** the payment-form-filling and confirmation-detection logic that actually completes a purchase is an incomplete stub. No automated purchase can finish end-to-end today.

### 11. Delivery
Tracked via AfterShip across TCS/Leopards/PostEx/M&P couriers; status pushed to the customer via notification. `delivered` status is intended to trigger installment-schedule activation. **Known gap (GW-BL-15):** this trigger is not currently wired.

### 12. Installments
Biweekly auto-debit attempts on due date (9 AM, retried same day 6 PM, next day 9 AM, day+2 12 PM, then flagged for manual collections outreach). Full detail: [`08-payment-workflow.md`](08-payment-workflow.md), [`10-default-collections-workflow.md`](10-default-collections-workflow.md). **Known gap (LS-CRIT-04):** the billing sweep that detects due installments does not currently trigger an actual payment-gateway charge — this link is missing end-to-end.

## Cancellation exit points

A customer can cancel while the order is in `url_submitted`, `offer_presented`, `offer_accepted`, or `extraction_failed`. **Known gap (GW-BL-04):** there is currently no cancellation path once contracts are signed but before a VCN is issued or money collected — a dead end for both the customer and admin as of the last audit. See [`09-refund-cancellation-workflow.md`](09-refund-cancellation-workflow.md).

## Related documents

[`07-bnpl-workflow-e2e.md`](07-bnpl-workflow-e2e.md) (system-internal view of the same flow), [`../03-bnpl-financing/16-financing-state-machine.md`](../03-bnpl-financing/16-financing-state-machine.md), [`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md).
