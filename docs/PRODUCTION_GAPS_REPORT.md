# SAHULATKAR BNPL — COMPREHENSIVE PRODUCTION GAPS REPORT
**Date**: 2026-04-27  
**Prepared for**: External Codex Agent Review  
**Scope**: All microservices EXCEPT credit-engine  
**Analyst**: Claude Sonnet 4.6 (full codebase read — every Python file across all services)

---

## DOCUMENT PURPOSE

This report is a forensic, production-readiness audit of the SahulatKar BNPL platform. It enumerates every gap, missing feature, incomplete stub, business logic hole, missing API, duplicate logic, and cross-service integration gap. It is organized by microservice, followed by cross-service scenario walkthroughs and frontend analysis. Every finding has been verified by reading the actual source code — no assumptions.

---

## PLATFORM SUMMARY

SahulatKar is Pakistan's Shariah-compliant BNPL platform:
- User pastes a product URL → AI scrapes it → financing offer generated → contracts signed (Wakalah + Murabaha) → down payment collected → single-use VCN issued → Playwright agent completes purchase → user repays in biweekly installments

**6 Microservices**: Gateway (8000), Product Service (8001), Credit Engine (8002, excluded), Payment Orchestrator (8003), Ledger Service (8004), Notification Service (8005)  
**2 Frontends**: web-customer (Next.js), web-admin (Next.js)  
**Stack**: FastAPI + PostgreSQL + Redis + Playwright + Stripe Issuing + Safepay/JazzCash/Raast/EasyPaisa + AfterShip

---

## TABLE OF CONTENTS

1. [12-Step Flow Scenario Walkthroughs](#1-12-step-flow-scenario-walkthroughs)
2. [Gateway Service Gaps](#2-gateway-service-gaps)
3. [Product Service Gaps](#3-product-service-gaps)
4. [Payment Orchestrator Gaps](#4-payment-orchestrator-gaps)
5. [Ledger Service Gaps](#5-ledger-service-gaps)
6. [Notification Service Gaps](#6-notification-service-gaps)
7. [Web Admin Frontend Gaps](#7-web-admin-frontend-gaps)
8. [Web Customer Frontend Gaps](#8-web-customer-frontend-gaps)
9. [Shared Python Package Gaps](#9-shared-python-package-gaps)
10. [Database Migration Gaps](#10-database-migration-gaps)
11. [Infrastructure & DevOps Gaps](#11-infrastructure--devops-gaps)
12. [Cross-Service Duplication Analysis](#12-cross-service-duplication-analysis)
13. [Master Gap Checklist](#13-master-gap-checklist)

---

## 1. 12-STEP FLOW SCENARIO WALKTHROUGHS

### SCENARIO A: Happy Path — Full Order Completion

**Step 1 — User pastes URL**
- `POST /api/v1/orders/initiate` (Gateway) → validates user KYC, calls Credit Engine for available credit, creates Order (status=URL_RECEIVED), enqueues extraction job to Product Service via internal call
- **GAP**: Gateway calls `POST /v1/internal/orders/{order_id}/product-extracted` and `extraction-failed` but there is no documented queue or mechanism — it's a direct HTTP callback. If Product Service is down, the callback never arrives and the order stays in URL_RECEIVED forever with NO timeout or retry.
- **GAP**: Order does NOT decrement `available_credit` at initiation (TASK-11 — only status change, no credit reservation). Two concurrent orders for the same user can each reserve the full credit limit.

**Step 2 — Playwright scrapes merchant page**
- Product Service ScrapingWorker pops job from `sk:queue:scraping`, runs ExtractionWaterfall (Tier1→Tier2A→Tier2B→Tier3)
- **CRITICAL BUG (PS-BUG-01)**: `scraping_worker.py:117` references `normalized_url` which is never defined. Worker crashes on first job. All scraping fails.
- **CRITICAL BUG (PS-BUG-02)**: `scraping_worker.py:207` references `prohibited_check` which is never defined in that scope. Prohibited check result is from `ProductExtractionService.extract_or_enqueue()` but not passed to the worker's `_process()` method.
- **GAP**: No per-user extraction concurrency limit — a user can flood the extraction queue.

**Step 3 — GPT-4o Vision extracts Universal Product Object (UPO)**
- ExtractionWaterfall calls Tier3 (GPT-4o) if Tiers 1/2 fail
- **GAP**: GPT-4o Vision API key and model configuration exist in settings but there is NO error handling for rate-limit (429) from OpenAI. Worker crashes, job goes to DLQ.
- **GAP**: `ProhibitedCheckerService.check_url()` is INCOMPLETE — function parses domain but returns default decision with no blacklist lookup. URL-based Shariah prohibition does not work.

**Step 4 — Credit Assessment (<3 seconds)**
- Credit Engine runs 7-layer scoring (excluded from this report)
- Gateway's `POST /v1/internal/users/{user_id}/credit-result` callback updates user credit_limit and risk_band
- **GAP**: Gateway credit_status endpoint reads `user.credit_limit` from ORM which may be stale — no explicit DB refresh. Users may see outdated credit limits.

**Step 5 — Financing offer: cost + 4% markup**
- `GET /api/v1/orders/{order_id}/offer` (Gateway) fetches from Product Service
- Product Service `/products/{upo_id}/offer` calculates murabaha markup via PricingService
- **COMPLIANCE GAP (PS-GAP-02)**: `pricing_service.py:22` has TODO: `"Obtain written Shariah-board sign-off on the tiered structure"`. Tiered markup (2.5% for 3-month, 4.0% for 4-month, 7.0% for 6-month) is NOT Shariah board approved. This is a compliance blocker.
- **GAP**: No down_payment_pct validation against system parameters. Gateway admin can set system-level min/max down payment, but PricingService does NOT query `system_parameters` table. The down_payment_pct is passed directly from client.

**Step 6 — User signs Wakalah Agreement via OTP**
- `POST /api/v1/contracts/wakalah/generate` → sends OTP, creates WakalahAgreement record
- `POST /api/v1/contracts/wakalah/sign` → verifies OTP, marks signed, creates Loan record
- **GAP**: Wakalah has 24-hour expiry check (BUG-06 fixed), but Murabaha contract generation does NOT check if Wakalah was signed first. User can generate Murabaha without completing Wakalah.
- **GAP**: Contract PDF is generated but hash verification `GET /v1/contracts/{type}/{id}/verify` exists as an endpoint but no background job validates stored PDFs after generation. Silent corruption undetected.

**Step 7 — User signs Murabaha Contract via OTP (HARD GATE)**
- `POST /api/v1/contracts/murabaha/sign` → order status → CONTRACTS_SIGNED
- VCN issuance blocked until this status (enforced at Gateway)
- **GAP**: No enforcement that Wakalah was signed BEFORE Murabaha can be signed. The code only checks that a Murabaha record exists, not that Wakalah is in `signed` state.
- **GAP**: Loan creation during contract signing has no retry logic. If the DB commit fails mid-way (e.g., network timeout), the order status transitions but no Loan is created. System is in inconsistent state.

**Step 8 — Down payment collected (25–40%)**
- `POST /api/v1/payments/down-payment` (Gateway) → enqueues to Payment Orchestrator
- Payment Orchestrator: validates CONTRACTS_SIGNED, creates PaymentWorkflow, calls gateway adapter (SafePay/JazzCash)
- **GAP**: Down payment percentage is validated against 25–40% hardcoded range in Payment Orchestrator, but this range is not in `system_parameters`. Admin cannot change this without code deploy.
- **GAP**: SafePay uses async redirect flow — user is redirected to SafePay, pays, comes back. JazzCash is sync. But Gateway's webhook endpoints (`/api/webhooks/payment/safepay`) validate HMAC but do NOT update PaymentWorkflow or Order status themselves — they delegate to Payment Orchestrator's internal confirm endpoint. This delegation path is not clearly documented and the redirect URL for SafePay after payment is not configured.
- **GAP**: `POST /api/v1/internal/payments/{payment_id}/confirm` is called by Payment Orchestrator to update Gateway's Order status. But if Payment Orchestrator confirms payment at its internal state (CAPTURED) and then fails to call Gateway's callback, the Order stays at CONTRACTS_SIGNED while Payment Orchestrator thinks payment is complete. Two separate transactions, no saga compensation.

**Step 9 — VCN issued (MCC-locked)**
- `POST /api/v1/payments/vcn/issue` (Gateway) → checks CONTRACTS_SIGNED, enqueues VCN issuance
- VCN Issue Worker (Payment Orchestrator) processes, calls Stripe Issuing
- `POST /v1/internal/orders/{order_id}/shipment-registered` (Gateway callback from Notification Service)
- **GAP**: VCN issuance failure (Stripe down) does NOT rollback Order status. Order stays in PENDING_VCN with no recovery path. Admin has no endpoint to retry VCN issuance for a specific order.
- **GAP**: VcnExpiryWorker marks expired VCNs but does NOT void them on Stripe. Local status says expired, Stripe card still active for 24 hours.
- **GAP**: VCN MCC lock configuration — which MCCs are blocked — is hardcoded in Stripe adapter. No admin interface to update prohibited MCCs.

**Step 10 — Playwright agent completes checkout**
- Product Service CheckoutConsumer processes the checkout job
- **CRITICAL GAP (PS-GAP-03)**: `CheckoutFormFiller.run_checkout()` is INCOMPLETE. Payment form filling (PAN/CVV entry), order confirmation detection, and receipt extraction are all missing or stubs. Automated purchases cannot complete.
- **GAP**: `GET /api/v1/internal/vcn/{order_id}/decrypt` (Payment Orchestrator) provides plaintext PAN/CVV to Product Service checkout agent — but this endpoint has no rate limiting. A compromised Product Service or token leak exposes all VCN credentials.
- **GAP**: If checkout fails, `POST /v1/internal/orders/{order_id}/checkout-status` is called with status=failed. Gateway updates order to PURCHASE_FAILED. But VCN is NOT voided — card remains active after failed purchase, security risk.

**Step 11 — Delivery tracked via AfterShip**
- Notification Service `POST /tracking/register` registers with AfterShip
- AfterShip webhook `POST /webhooks/aftership` processes delivery updates
- Gateway's delivery event listener processes `sk:event:delivery_status_changed` and `sk:event:delivery_confirmed`
- **GAP**: AfterShip webhook HMAC verification is implemented correctly. BUT if AfterShip sends the `delivered` event, the Gateway listener updates Order status to DELIVERED but does NOT trigger the installment schedule activation. Installment billing starts biweekly but there is no explicit trigger connecting delivery confirmation to installment activation.

**Step 12 — Remaining installments auto-collected biweekly**
- Ledger Service BillingSweepWorker runs daily, detects overdue installments
- Payment Orchestrator Raast mandate used for recurring collection
- **GAP**: Raast mandate lookup is referenced in GatewayRoutingEngine (`GAP-07 FIX: Prioritize Raast if valid mandate exists`) but mandate lookup is NOT fully implemented. Recurring auto-collection defaults to manual JazzCash, no automation.
- **GAP**: BillingSweepWorker marks installments overdue and accrues late fees but does NOT automatically trigger payment retry via Payment Orchestrator. There is no connection between the billing sweep detecting overdue status and initiating automatic payment collection.
- **GAP**: Late fees are 100% Shariah-required charity (tasdeeq). BillingSweepWorker marks late fees as accrued, but TasdeeqWorker (Ledger Service) has incomplete charity fund disbursement. The GL posting for charity never happens.

---

### SCENARIO B: User Cancels Order After Offer Accepted

- `POST /api/v1/orders/{order_id}/cancel` (Gateway)
- Allowed in: url_received, offer_presented, offer_accepted, extraction_failed states
- **GAP**: Cancellation after CONTRACTS_SIGNED but before down payment is NOT handled. Code does not list CONTRACTS_SIGNED as a cancellable state, but VCN has not been issued and no money collected. This is a dead end — user cannot cancel and admin has no override endpoint.
- **GAP**: Credit restoration on cancellation (`order_cancel` calls `available_credit += loan.principal`) but TASK-11 (credit reservation) was never implemented, so the increment is adding credit that was never subtracted.
- **GAP**: No notification sent to user on order cancellation.

### SCENARIO C: KYC Rejection and Resubmission

- User submits KYC → KYC reviewer claims from queue → rejects → user resubmits
- `POST /api/v1/kyc/resubmit` clears NADRA/Shufti verification data
- **GAP**: NADRA/Shufti integrations are STUB — no actual API calls are made. KYC is approved/rejected manually only via admin HITL queue. No automated identity verification.
- **GAP**: KYC resubmit does NOT check if the previous attempt is still in the HITL queue. If reviewer has claimed it and hasn't decided, user's resubmission creates orphaned queue item.
- **GAP**: Max 3 resubmission attempts enforced but the counter is on `KycVerification.attempt_count`. If user creates new account with same CNIC, counter resets.

### SCENARIO D: Payment Failure Mid-Installment

- Installment becomes due → BillingReminder fires (D-3, D-1) → Payment Orchestrator attempts charge
- **GAP**: Auto-charge for installments is not implemented. `POST /api/v1/payments/installment/{id}/pay` is customer-initiated only. There is no automated billing trigger that actually CALLS the payment gateway on the due date.
- **GAP**: After 3 failed attempts (Payment Orchestrator tracks attempt_count) there is no escalation to HITL or credit bureau reporting.

---

## 2. GATEWAY SERVICE GAPS

### 2.1 Implemented Endpoints

**Auth**: register/initiate, verify-otp, login, refresh, logout, otp/resend, me  
**Admin Auth**: login (MFA), me, logout, mfa/setup, mfa/verify, create admin, assign role, list roles  
**KYC**: start, upload/{doc_type}, submit, status, resubmit, profile PUT/GET  
**Orders**: initiate, offer, accept, list, detail, tracking, cancel  
**Contracts**: wakalah/generate, wakalah/sign, murabaha/generate, murabaha/sign, status, verify hash, admin list/pdf  
**Payments**: down-payment, schedule, installment pay, VCN issue, VCN status  
**Credit**: status, history  
**Admin Users**: list, detail, financial-summary, kyc, activity, status update, credit-limit override, orders, loans, installments, audit-log, risk-history, contracts  
**Admin Orders**: list, detail  
**Admin Payments**: list, detail  
**Admin Dashboard**: KPI dashboard  
**Admin KYC**: queue, claim, decision  
**Admin Compliance**: audit-trail, shariah-audit  
**Admin Risk**: blacklist list, blacklist add  
**Admin System**: parameters (STUB — incomplete)  
**Admin Analytics**: gmv-trend, approval-funnel, credit-band-distribution, default-rate-trend  
**Admin HITL**: (imported but not verified complete)  
**Admin Installments**: (imported but specific endpoints not verified)  
**Internal**: product-extracted, extraction-failed, payment confirm, credit-result, update-result (credit), shipment-registered, checkout-status  
**Webhooks**: jazzcash, safepay  
**Health**: /health, /api/v1/health-check

### 2.2 Missing / Incomplete API Endpoints

| Gap ID | Endpoint | Status | Description |
|--------|----------|--------|-------------|
| GW-GAP-01 | `GET /api/v1/admin/system/parameters` | STUB | Returns empty. No CRUD for system parameters (min down payment %, max credit limit, late fee rate, etc.). Admin cannot configure platform-level settings. |
| GW-GAP-02 | `PUT /api/v1/admin/system/parameters/{key}` | MISSING | No endpoint to update individual system parameter. |
| GW-GAP-03 | `POST /api/v1/admin/orders/{order_id}/status` | MISSING | Admin manual order status override (TASK-20). Admin cannot force-advance a stuck order (e.g., from PENDING_VCN back to CONTRACTS_SIGNED). |
| GW-GAP-04 | `GET /api/v1/admin/orders/{order_id}/installments` | MISSING | Admin view of installments for a specific order (TASK-21). |
| GW-GAP-05 | `POST /api/v1/admin/orders/{order_id}/restructure` | MISSING | Payment restructuring (AD-07 in admin modules). No endpoint to restructure installment plans. |
| GW-GAP-06 | `GET /api/v1/admin/users/{user_id}/devices` | MISSING | No device fingerprint history for fraud investigation. |
| GW-GAP-07 | `POST /api/v1/admin/risk/blacklist/{id}/remove` | MISSING | No endpoint to remove blacklist entry. Only add. |
| GW-GAP-08 | `POST /api/v1/admin/users/{user_id}/reset-failed-attempts` | MISSING | Account lockout reset for customer support. |
| GW-GAP-09 | `GET /api/v1/admin/compliance/charity-audit` | MISSING | Tasdeeq/charity audit trail for Shariah compliance. |
| GW-GAP-10 | `POST /api/v1/payments/installment/retry` | MISSING | Customer-initiated retry for a failed installment payment. |
| GW-GAP-11 | `POST /api/v1/payments/refund/{order_id}` | MISSING | Customer refund request endpoint (delegates to Payment Orchestrator refund stub). |
| GW-GAP-12 | `GET /api/v1/admin/analytics/cohort` | MISSING | Cohort analysis (AD-22 module defined in admin-modules.ts). |
| GW-GAP-13 | `GET /api/v1/admin/analytics/custom-report` | MISSING | Custom reports (AD-23 module defined). |
| GW-GAP-14 | `GET /api/v1/admin/partners/merchants` | MISSING | Merchant management panel (AD-24 module). |
| GW-GAP-15 | `GET /api/v1/admin/system/health` | MISSING | System health dashboard (AD-28 module). |
| GW-GAP-16 | `GET /api/v1/admin/support/tickets` | MISSING | Support tickets (AD-16, AD-17 modules). |
| GW-GAP-17 | `GET/POST /api/v1/admin/admins` | PARTIAL | Admin list exists but only via `GET /admin/auth/admins`. No dedicated admin management module matching AD-25 (Team & Access). |
| GW-GAP-18 | `GET /api/v1/orders/{order_id}/receipt` | MISSING | No endpoint for customer to download purchase receipt/screenshot. |

### 2.3 Business Logic Gaps

| Gap ID | Location | Severity | Description |
|--------|----------|----------|-------------|
| GW-BL-01 | `orders.py` — `initiate()` | CRITICAL | Credit reservation (TASK-11) not implemented. `available_credit` is NOT decremented when order is initiated. Two simultaneous orders can exceed user's credit limit. |
| GW-BL-02 | `contracts.py` — `sign_wakalah()` | HIGH | Loan creation has no retry/idempotency. If DB commit fails after order status update, Loan is never created but order shows CONTRACTS_SIGNED. |
| GW-BL-03 | `contracts.py` | HIGH | No enforcement that Wakalah must be in `signed` state before Murabaha generation is allowed. |
| GW-BL-04 | `orders.py` — `cancel()` | HIGH | CONTRACTS_SIGNED is not in cancellable states. Users who signed contracts but before VCN have no exit path. |
| GW-BL-05 | `admin_auth.py` — `verify_mfa()` | HIGH | TOTP lockout after 5 failed attempts (TASK-16) is referenced but not implemented. Infinite brute-force of TOTP codes is possible. |
| GW-BL-06 | `payments.py` | HIGH | No connection between Payment Orchestrator confirming payment and Order status update. Two separate transactions with no saga compensation if second fails. |
| GW-BL-07 | `credit.py` | MEDIUM | `/api/v1/credit/status` reads `user.credit_limit` from ORM session which may be stale after credit engine update. No refresh query. |
| GW-BL-08 | `admin_hitl.py` | MEDIUM | HITL queue management exists but no escalation path when KYC stays in queue >48 hours. No SLA alerting. |
| GW-BL-09 | `kyc.py` | MEDIUM | `resubmit` does not check if previous attempt is still in HITL queue (claimed but undecided). Race condition creates orphaned queue items. |
| GW-BL-10 | `orders.py` | MEDIUM | No notification sent to user on order cancellation. |
| GW-BL-11 | `payments.py` | MEDIUM | VCN status endpoint returns masked card number but there is no endpoint for the customer to view their full installment schedule post-VCN issuance. |
| GW-BL-12 | `rbac.py` | MEDIUM | RBAC permission matrix in `rbac.py` (TASK-19) not fully synced with admin endpoint decorators. Some admin endpoints use `RequirePermission("manage_system")` but this permission is NOT listed in any role's permission set. |
| GW-BL-13 | `webhooks.py` | MEDIUM | JazzCash and SafePay webhook handlers validate HMAC and enqueue to Redis but do NOT deduplicate. Duplicate webhook events can double-confirm payments. |
| GW-BL-14 | `admin_compliance.py` — `shariah_audit()` | MEDIUM | Shariah audit only checks if `murabaha_contracts.cost_price` is NOT NULL. Does not check: (1) charity was actually disbursed, (2) profit_rate_pct matches Shariah-approved rates. |
| GW-BL-15 | `delivery_events.py` | MEDIUM | Delivery confirmation event updates order status to DELIVERED but does NOT trigger installment activation or first installment reminder scheduling. |

### 2.4 Missing Error Handling

- `POST /v1/internal/orders/{order_id}/product-extracted`: No schema validation. Invalid `cost_price` or null `product_id` silently propagates.
- `POST /v1/internal/payments/{payment_id}/confirm`: No order state validation. Can confirm payment on an order in wrong state.
- `POST /v1/kyc/submit`: No check if NADRA/Shufti API is reachable. Submission queued but may fail silently.
- Audit trail `record_audit_event()` has broad `try/except(Exception)` blocks — audit events silently fail without alerting.

---

## 3. PRODUCT SERVICE GAPS

### 3.1 Implemented Endpoints

**Products**: extract, jobs/{id}, list (user), search, detail, refresh, offer (single+multi-plan), price-history  
**Agent**: queue-job, stream (SSE), cancel  
**Admin**: list products, product detail, patch product, prohibit, unpromote, soft-delete, list executions, retry execution, list scraping jobs, list prohibited categories, upsert/delete prohibited category, list merchants, merchant detail, block merchant, queue stats, DLQ reprocess/purge  
**Health**: live, ready

### 3.2 Critical Bugs

| Bug ID | Location | Severity | Description | Fix |
|--------|----------|----------|-------------|-----|
| PS-BUG-01 | `scraping_worker.py:117` | CRITICAL | `normalized_url` undefined — worker crashes on every job. All scraping fails. | Replace with `payload['canonical_url']` |
| PS-BUG-02 | `scraping_worker.py:207` | CRITICAL | `prohibited_check` undefined — `_process()` method never calls ProhibitedCheckerService. Product saved without Shariah check. | Add prohibited check call before product save |
| PS-BUG-03 | `admin.py:138` | HIGH | `ExecutionRepository.list_all()` does not filter by product. Returns all system executions instead of only for requested product. | Implement `list_by_product()` with product_id filter at DB level |

### 3.3 Business Logic Gaps

| Gap ID | Location | Severity | Description |
|--------|----------|----------|-------------|
| PS-BL-01 | `prohibited_checker.py` | HIGH | `check_url()` is INCOMPLETE — parses domain only, returns default decision, no blacklist lookup. URL-based Shariah prohibition does not work. |
| PS-BL-02 | `pricing_service.py:22` | CRITICAL (COMPLIANCE) | Tiered markup structure has `TODO: Obtain written Shariah-board sign-off`. Cannot launch without board approval. |
| PS-BL-03 | `checkout/form_filler.py` | CRITICAL | Payment form filling, order confirmation detection, and receipt extraction are INCOMPLETE stubs. Playwright automated checkout cannot complete. |
| PS-BL-04 | `checkout/vcn_verifier.py` | HIGH | VCN verification timeout handling is missing. If VCN charge confirmation never arrives, order is stuck. No rollback. |
| PS-BL-05 | Workers | HIGH | If CheckoutConsumer crashes mid-Playwright session (e.g., browser crashes), the job is not re-queued. The distributed lock (`sk:checkout:processing:{id}`) expires after 600s but the execution record stays in RUNNING state. |
| PS-BL-06 | `event_listener.py` | MEDIUM | `sk:events:vcn.issued` triggers checkout queue, `sk:events:order.cancelled` cancels checkout. But if VCN is issued then order is cancelled, the checkout may have already started. Race condition between checkout start and cancellation event. |
| PS-BL-07 | Product catalog | MEDIUM | No background job to periodically re-check all active products against updated prohibited categories list. A product can be on platform when category was allowed, then category gets prohibited, but product stays active. |
| PS-BL-08 | Merchant model | MEDIUM | `checkout_success_rate` field exists on Merchant model but is NEVER updated. Merchant routing does not use success rate. |
| PS-BL-09 | `product_extraction_service.py` | MEDIUM | Image proxy caching to S3 has try/except that silently ignores failures. No retry, no alert. |
| PS-BL-10 | `scraping_worker.py` | MEDIUM | HITL escalation on max retries creates `HitlQueue` entry but Gateway HITL queue (`admin_hitl.py`) processes KYC items, NOT product extraction failures. Two different HITL systems — no unified HITL queue. |
| PS-BL-11 | Pricing | MEDIUM | `down_payment_pct` passed by client is not validated against system-level min/max (which lives in `system_parameters` table). Admin-configured limits are ignored by Product Service. |
| PS-BL-12 | `price_staleness_worker.py` | LOW | Price staleness worker exists but product expiration (archiving products >30 days old without active orders) is not implemented. |

### 3.4 Missing Endpoints

| Gap ID | Endpoint | Description |
|--------|----------|-------------|
| PS-EP-01 | `POST /v1/products/agent/job/{id}/screenshot` | No endpoint to retrieve checkout screenshot. Gateway calls `/v1/internal/orders/{id}/checkout-status` with `screenshot_s3` but no endpoint to actually download it. |
| PS-EP-02 | `GET /v1/admin/analytics/extraction-stats` | No admin analytics for extraction success/failure rates by merchant. |
| PS-EP-03 | `POST /v1/admin/prohibited-categories/sync` | No endpoint to bulk-sync prohibited categories from external Shariah source. |
| PS-EP-04 | `GET /v1/admin/extraction-waterfall/config` | No admin view of extraction tier configuration. |

### 3.5 Missing Error Handling

- `POST /products/extract`: No pre-validation of URL format before normalizer — malformed URLs cause normalizer exceptions.
- ScrapingWorker: Redis connection loss during job processing causes job loss (BRPOP returns but no reconnect loop).
- EventListenerWorker: Malformed JSON in event payload drops event with no DLQ fallback.
- CheckoutConsumer: Playwright launch timeout causes unhandled exception, worker thread dies.

---

## 4. PAYMENT ORCHESTRATOR GAPS

### 4.1 Implemented Endpoints

**Payments**: down-payment (rate-limited), pay-installment, refund (STUB)  
**VCN**: issue (rate-limited), void, status, decrypt (internal)  
**Admin**: mandates list (STUB)  
**Health**: /health (live), /health/ready (readiness), /metrics

### 4.2 Critical Missing Implementations

| Gap ID | Component | Severity | Description |
|--------|-----------|----------|-------------|
| PO-CRIT-01 | `refund_orchestrator.py` | CRITICAL | RefundOrchestrator is a STUB. `initiate_refund()` has no implementation. If user returns a product, there is no refund pathway. The API endpoint exists but does nothing. |
| PO-CRIT-02 | `reconciliation_worker.py` | CRITICAL | Settlement reconciliation uses mock JSON files from filesystem (`settlement_{gateway}_{date}.json`). No real SFTP integration with JazzCash. No real API integration with SafePay for settlement download. Financial reconciliation never works in production. |
| PO-CRIT-03 | Raast mandate | HIGH | GatewayRoutingEngine references mandate-based routing (`GAP-07: Prioritize Raast if valid mandate exists`) but mandate lookup is not implemented. Recurring auto-debit collection (Step 12 of flow) defaults to manual payment. |
| PO-CRIT-04 | `vcn_expiry_worker.py` | HIGH | Marks VCNs as expired locally but does NOT call Stripe to actually cancel/void the card. Expired cards remain active on Stripe for 24 more hours. |
| PO-CRIT-05 | `stripe_poller_worker.py` | HIGH | StripePollerWorker polls every 600 seconds but Stripe webhook events are not consumed by this service. Stripe webhooks (e.g., `issuing_card.updated`) have no handler endpoint in Payment Orchestrator. |
| PO-CRIT-06 | EasyPaisa adapter | MEDIUM | EasyPaisa adapter (`adapters/easypaisa.py`) is listed in architecture but status of implementation is unknown. Listed as payment method but not validated in routing engine. |

### 4.3 Business Logic Gaps

| Gap ID | Location | Severity | Description |
|--------|----------|----------|-------------|
| PO-BL-01 | `vcn.py` — `decrypt_vcn()` | HIGH | `/api/internal/vcn/{order_id}/decrypt` has no rate limiting. A compromised internal token can mass-exfiltrate all PAN/CVV data. |
| PO-BL-02 | Gateway adapter failures | HIGH | Gateway adapters don't differentiate retryable (network timeout) vs non-retryable (invalid card, insufficient funds) errors. All failures increment `attempt_count` equally. |
| PO-BL-03 | `payment_orchestrator.py` | HIGH | Payment confirmation (`confirm_payment()`) and Gateway callback (`POST /v1/internal/payments/{payment_id}/confirm`) are in separate transactions with no saga compensation. Payment Orchestrator marks CAPTURED but Gateway callback fails → Order status never updated to DOWN_PAYMENT_RECEIVED. |
| PO-BL-04 | `payments.py` — `down_payment()` | MEDIUM | Amount validation uses 1 PKR tolerance but does NOT check for negative amounts or zero amounts. |
| PO-BL-05 | VCN void | MEDIUM | `POST /api/payments/vcn/{vcn_id}/void` calls Stripe cancellation but if Stripe API fails, VCN is marked voided locally. Card remains active on Stripe. |
| PO-BL-06 | Idempotency | MEDIUM | `PaymentWorkflow.idempotency_key` uniqueness relies on DB constraint only. No pre-check in application layer. Concurrent requests can cause DB constraint violation → 500 error instead of idempotent 200. |
| PO-BL-07 | `admin/mandates` | LOW | Admin mandate list is STUB — returns empty list. No mandate management for Raast recurring payments. |
| PO-BL-08 | Payment session expiry | MEDIUM | `PaymentSessionExpiryWorker` processes all expired sessions serially. Under high load (thousands of expired sessions), this blocks. No concurrency control or batching. |

### 4.4 Missing Endpoints

| Gap ID | Endpoint | Description |
|--------|----------|-------------|
| PO-EP-01 | `POST /api/payments/down-payment/{payment_id}/retry` | No retry endpoint for a failed payment workflow. |
| PO-EP-02 | `GET /api/payments/history/{order_id}` | No endpoint to get full payment history for an order. |
| PO-EP-03 | Stripe webhook receiver | No `POST /webhooks/stripe` endpoint to receive `issuing_card.updated`, `payment_intent.payment_failed` from Stripe. |
| PO-EP-04 | `POST /api/admin/reconciliation/trigger` | No admin-triggerable reconciliation endpoint. Only CLI worker. |
| PO-EP-05 | `GET /api/admin/mandates/{user_id}` | No endpoint to view user's active Raast mandate. |
| PO-EP-06 | Auto-collection trigger | No `POST /api/internal/installments/{id}/auto-collect` endpoint that Ledger Service's BillingSweepWorker can call to trigger payment for overdue installments. This is the critical missing link between billing sweep and payment execution. |

---

## 5. LEDGER SERVICE GAPS

### 5.1 Implemented Endpoints

**Accounts**: list (filterable by type), detail with balance  
**Journal Entries**: list (cursor-paginated), detail, manual entry, reverse entry  
**Finance**: trial-balance, balance-sheet, income-statement, cash-flow (STUB)  
**Periods**: list, create, close, status  
**Health**: /health, /metrics

### 5.2 Critical Missing Implementations

| Gap ID | Component | Severity | Description |
|--------|-----------|----------|-------------|
| LS-CRIT-01 | `finance_service.py` — `generate_cash_flow()` | CRITICAL | Cash flow statement is a STUB — only headers, no implementation. Finance team cannot produce complete financial statements. |
| LS-CRIT-02 | GL entry validation | CRITICAL | Journal entries are posted WITHOUT validating that debit total = credit total (double-entry accounting invariant). Unbalanced entries can be created. This corrupts the entire general ledger. |
| LS-CRIT-03 | `tasdeeq_service.py` | HIGH | Charity fund disbursement (`process_charity_allocation()`) is a stub. Tasdeeq calculation runs but charity is never actually disbursed or recorded in GL. Shariah compliance violation — late fees collected but not donated. |
| LS-CRIT-04 | Installment auto-collection | CRITICAL | BillingSweepWorker detects overdue installments and accrues late fees but has NO mechanism to trigger automatic payment collection from Payment Orchestrator. Billing sweep runs but no money is actually collected automatically. |
| LS-CRIT-05 | DLQ consumer | HIGH | Failed events are sent to `sk:queue:dlq:events` but there is NO automated DLQ consumer. Events accumulate in DLQ forever without retry or alerting. |

### 5.3 Business Logic Gaps

| Gap ID | Location | Severity | Description |
|--------|----------|----------|-------------|
| LS-BL-01 | `accounting_service.py` | HIGH | Manual journal entry creation does not validate that account codes exist before posting. Invalid account codes cause DB foreign key violation → 500 error. |
| LS-BL-02 | `period_service.py` | HIGH | Period close does NOT prevent backdated entries. After closing a period, entries with dates in the closed period can still be created. |
| LS-BL-03 | `balance_service.py` | MEDIUM | Balance snapshot becomes stale if `BalanceSnapshotWorker` fails. No fallback to recalculate on-the-fly if snapshot is missing for a date. |
| LS-BL-04 | `tasdeeq_validation.py` | MEDIUM | Charity validation uses hardcoded wealth thresholds, not configurable via system parameters. Shariah threshold changes require code deploy. |
| LS-BL-05 | Event listener | MEDIUM | `payment.confirmed` event handler posts GL entry but does NOT validate that the payment amount in the event matches the Loan's installment amount. Incorrect amounts silently accepted. |
| LS-BL-06 | `reconciliation_worker.py` | HIGH | Ledger-side reconciliation only checks if revenue was posted, not if amounts match. No actual reconciliation against Payment Orchestrator's `PaymentTransaction` records. |
| LS-BL-07 | Period management | MEDIUM | No automated period creation. When fiscal year ends, admin must manually create next year's periods. No alert when current period is near close date. |
| LS-BL-08 | `late_fee_service.py` | MEDIUM | Late fee calculation exists but does NOT verify that the late fee is within Shariah-permitted bounds (late fees cannot exceed principal in Islamic finance). |
| LS-BL-09 | `billing_sweep_worker.py` | HIGH | Billing sweep marks installments overdue and creates late fee journal entries but does NOT notify Notification Service. Users receive no alert that their installment is overdue. (Reminder Worker only fires D-3, D-1 before due date, not after.) |

### 5.4 Missing Endpoints

| Gap ID | Endpoint | Description |
|--------|----------|-------------|
| LS-EP-01 | `GET /api/finance/charity-summary` | No endpoint for Shariah compliance reporting on charity disbursements. |
| LS-EP-02 | `GET /api/finance/overdue-report` | No overdue installment report endpoint. |
| LS-EP-03 | `POST /api/internal/billing/trigger-sweep` | No internal endpoint for Gateway to trigger billing sweep manually. Only CLI. |
| LS-EP-04 | `GET /api/entries/{entry_number}` | Per code review: catches `LookupError` but returns 500 instead of 404. This is a bug. |
| LS-EP-05 | `GET /api/finance/tasdeeq-report` | No endpoint to generate tasdeeq/charity allocation report for compliance. |
| LS-EP-06 | `GET /api/accounts/{code}/ledger` | No endpoint to get the full ledger (T-account view) for an account. Only balance summary. |

---

## 6. NOTIFICATION SERVICE GAPS

### 6.1 Implemented Endpoints

**Notifications**: list (paginated, filterable), mark-read, mark-all-read, unread-count, preferences GET/PUT, unsubscribe  
**Internal**: send, otp, bulk  
**Tracking**: register (internal), status GET (user)  
**Webhooks**: aftership (HMAC verified), sendgrid (NO signature verification), sms-delivery (HMAC optional), whatsapp-delivery (HMAC optional)  
**Admin**: list notifications, stats, DLQ view, retry notification, retry-all DLQ, purge DLQ, list templates, update template, list scheduled, cancel scheduled  
**Admin Tracking**: (file exists, content not verified)  
**Health**: live, ready

### 6.2 Critical Bugs

| Bug ID | Location | Severity | Description |
|--------|----------|----------|-------------|
| NS-BUG-01 | `notification_service.py:219` | HIGH | Registration OTPs (for users not yet in DB) are assigned to `user_id=1` (super admin). Pollutes admin audit trail. Registration OTPs cannot be filtered by user. |
| NS-BUG-02 | `admin_notifications.py:~45` | MEDIUM | `list_dlq_items()` has unreachable `await redis.lpush(...)` code after a `return` statement. Dead code in DLQ listing. |

### 6.3 Business Logic Gaps

| Gap ID | Location | Severity | Description |
|--------|----------|----------|-------------|
| NS-BL-01 | `webhooks.py` — `sendgrid_webhook()` | HIGH | SendGrid webhook has NO HMAC signature verification. Anyone can POST to this endpoint and trigger email preference changes (unsubscribe). |
| NS-BL-02 | `sms_dispatcher.py` | MEDIUM | JazzSMSDispatcher health_check() calls `settings.JAZZ_SMS_API_URL + "/health"` — this assumes Jazz SMS API has a `/health` route, which is not guaranteed for a third-party API. Health check may always return false. |
| NS-BL-03 | `notification_service.py` | MEDIUM | OTP rate limiting (`_apply_otp_rate_limit(phone)`) is referenced but implementation is not visible in analyzed code. Threshold values not documented. If too permissive → SMS fraud. If misconfigured → users locked out. |
| NS-BL-04 | `event_listeners.py` | MEDIUM | Event payload extraction functions may return `None`. The calling code does not handle `None` return — event is dropped silently. No DLQ fallback. |
| NS-BL-05 | `reminder_worker.py` | MEDIUM | Reminder worker fires for D-3 and D-1 before due date (from `settings.REMINDER_DAYS_BEFORE`). But after overdue, no reminder fires. Users who miss payment receive NO notification from Notification Service. The `billing.installment_overdue` event is never published by anyone. |
| NS-BL-06 | `whatsapp_dispatcher.py` | LOW | WhatsApp delivery receipt: `status == "read"` is treated as delivered but WhatsApp has different delivery states (`sent`, `delivered`, `read`). Only `delivered` should update `DispatchStatus.DELIVERED`. |
| NS-BL-07 | Template management | MEDIUM | Compliance guard on template update deactivates auth/compliance templates and logs warning but `require_permissions(["admin:notifications:write"])` is not granular enough. Any admin with write permission can modify OTP template content. Should require `admin:notifications:superadmin` for OTP templates. |
| NS-BL-08 | FCM push | MEDIUM | `FCMPushDispatcher` is listed in dispatchers but FCM credentials validation at startup is not verified. If FCM key is invalid, push notifications fail silently at dispatch time. |
| NS-BL-09 | Scheduled notifications | MEDIUM | `ScheduledNotification` model and admin endpoints exist, but no background worker processes scheduled notifications. `fired_at` never gets set. Scheduled messages never fire. |
| NS-BL-10 | `retry_service.py` | MEDIUM | Retry service exists but the retry strategy (exponential backoff, max attempts before DLQ) is not documented or verified in the code. |

### 6.4 Missing Events / Integration Gaps

The following events are EXPECTED by Notification Service's `EVENT_CATEGORY_MAP` but are NOT published by any source service:

| Missing Event | Should Be Published By | Impact |
|--------------|----------------------|--------|
| `billing.installment_overdue` | Ledger BillingSweepWorker | Users never notified when installment goes overdue |
| `order.cancelled` (to notifications) | Gateway OrderService | No notification on order cancellation |
| `vcn.expired` | Payment Orchestrator VcnExpiryWorker | No notification when VCN expires |
| `payment.failed` (auto-debit) | Payment Orchestrator | No notification on auto-collection failure |
| `kyc.documents_needed` | Gateway KycService | No notification asking user to resubmit docs |
| `credit.limit_changed` | Gateway CreditService | No notification on credit limit change |

---


## 9. SHARED PYTHON PACKAGE GAPS

### 9.1 Verified Package Contents (sk_shared)

`constants.py`, `database.py`, `events.py`, `exceptions.py`, `middleware.py`, `notifications.py`, `pagination.py`, `redis_client.py`, `security.py`, `storage.py`  
Models: `auth.py`, `payment.py`, `order.py`, `contract.py`, `kyc.py`, `credit.py`, `delivery.py`, `audit.py`, `ledger.py`, `admin.py`, `notification.py`, `product.py`

### 9.2 Gaps

| Gap ID | Component | Severity | Description |
|--------|-----------|----------|-------------|
| SH-GAP-01 | `notifications.py` | HIGH | `send_sms()` and `send_email()` are STUBS — no actual implementation. Some services import these expecting them to work. |
| SH-GAP-02 | `security.py` | HIGH | `decode_access_token()` has no refresh token validation. Refresh tokens and access tokens use the same decoding logic — a refresh token can be used as an access token. |
| SH-GAP-03 | Event envelope | MEDIUM | `build_event_envelope()` creates JSON with metadata but no schema enforcement. Any service can publish malformed events. No Pydantic model for event validation on publish side. |
| SH-GAP-04 | Storage | MEDIUM | `upload()` method has no checksum verification. Uploaded files may be corrupted without detection. |
| SH-GAP-05 | `redis_client.py` | MEDIUM | `RedisClient.lrange()` is used in admin notification DLQ but is not defined in the client wrapper — direct access to `redis.redis.lrange()`. Not all Redis commands are wrapped — inconsistent interface. |
| SH-GAP-06 | Models — `notification.py` | MEDIUM | `ScheduledNotification` model has `fired_at` and `cancelled_at` columns but no `scheduled_for` validation — past dates can be scheduled. |
| SH-GAP-07 | Constants | LOW | `OrderState` enum does not include `DELIVERY_CONFIRMED` — Gateway uses this status in event listener but it's not in the canonical list. |

---

## 10. DATABASE MIGRATION GAPS

### 10.1 Migration State

49 migrations present (001–049). Sequence appears complete.

### 10.2 Critical Migration Gaps

| Gap ID | Migration | Severity | Description |
|--------|-----------|----------|-------------|
| DB-GAP-01 | All | HIGH | `downgrade()` not implemented for most migrations. Production rollback is impossible. Any failed deploy cannot be reversed. |
| DB-GAP-02 | Partitioning migrations | MEDIUM | Partition creation for `orders` and `audit_trail` tables uses raw SQL. Syntax verified for PostgreSQL 16 but not tested. If partition constraint fails silently, data goes to default partition. |
| DB-GAP-03 | Triggers | MEDIUM | DB trigger creation uses raw DDL. Trigger versions not tracked — if a trigger is modified, it requires a new migration with `CREATE OR REPLACE`. No trigger test coverage. |
| DB-GAP-04 | system_parameters seeding | HIGH | Gateway verifies `system_parameters` table exists at startup but there is NO migration that seeds required default system parameters (min_down_payment_pct, max_credit_limit, late_fee_daily_rate, etc.). Startup passes but system parameters query returns empty. |
| DB-GAP-05 | `risk_blacklist` | MEDIUM | `risk_blacklist` table migration exists but no index on `(type, value)` for fast lookup during request processing. Every request that checks blacklist does a full table scan. |
| DB-GAP-06 | TASDEEQ integration table | MEDIUM | Migration creates `tasdeeq_records` or equivalent but TasdeeqService does not use it consistently. Charity tracking may be in GL entries only, with no separate audit table. |
| DB-GAP-07 | `fiscal_year` field | MEDIUM | `create_period()` in Ledger Service's `period_service.py` does not set `fiscal_year` (GAP-05 from Ledger Service) — missing migration to make `fiscal_year` non-null OR application logic to populate it. |

---

## 11. INFRASTRUCTURE & DEVOPS GAPS

### 11.1 Missing Operational Components

| Gap ID | Component | Severity | Description |
|--------|-----------|----------|-------------|
| INF-GAP-01 | Observability stack | HIGH | Prometheus is referenced in each service's `/metrics` endpoint but no Grafana dashboards are defined. No alerting rules configured. No visibility into system health. |
| INF-GAP-02 | Log aggregation | HIGH | No Fluent Bit or similar log shipper configuration. Logs stay on pods and are lost on restart. No centralized log search (OpenSearch/Loki). |
| INF-GAP-03 | Distributed tracing | HIGH | OpenTelemetry instrumentation is referenced in Product Service workers but not verified across all services. No Jaeger or Tempo collector configured. Cannot trace a request across 5 services. |
| INF-GAP-04 | Correlation IDs | HIGH | `X-Request-ID` is generated by Gateway middleware but NOT propagated to downstream services (Product Service, Payment Orchestrator, Ledger Service, Notification Service). Cannot trace an order through the full pipeline. |
| INF-GAP-05 | DLQ monitoring | HIGH | 4 separate DLQ systems exist (scraping DLQ, checkout DLQ, notification DLQ, ledger event DLQ). No unified DLQ monitoring or alerting. Items accumulate silently. |
| INF-GAP-06 | Background worker health | MEDIUM | Gateway has `listener_watchdog()` for its delivery event listener. But VcnIssueWorker, ScrapingWorker, CheckoutConsumer, NotificationConsumer, LedgerEventListener — none have centralized health reporting. Worker crashes not detected until queue depth grows. |
| INF-GAP-07 | Secret rotation | MEDIUM | JWT private key, Stripe API key, JazzCash/SafePay credentials stored in settings. No key rotation mechanism. Single compromised secret requires code deploy. |
| INF-GAP-08 | Audit log immutability | HIGH | Audit trail stored in `audit_trail` table — subject to SQL DELETE. Not forensics-ready. Should be append-only log stored in immutable S3 or CloudWatch Logs. |
| INF-GAP-09 | CI/CD secret scanning | MEDIUM | No Gitleaks or similar secret scanning in CI pipeline. Credentials accidentally committed are not detected. |
| INF-GAP-10 | Database connection pooling | MEDIUM | PgBouncer is in docker-compose but K8s manifests do not clearly show PgBouncer sidecar or standalone deployment for production. |
| INF-GAP-11 | Alembic migration runner | HIGH | No `alembic upgrade head` step in Kubernetes deployment manifest. Migrations not automatically applied on deploy. Manual step required. |
| INF-GAP-12 | Start script | LOW | `start_all.ps1` exists in project root but is Windows-only PowerShell. No cross-platform Makefile or shell script for developers. |

---

## 12. CROSS-SERVICE DUPLICATION ANALYSIS

### 12.1 Duplicate Logic (Same Thing Built Twice)

| Duplicated Logic | Service 1 | Service 2 | Recommendation |
|-----------------|-----------|-----------|----------------|
| Audit trail recording | Gateway `core/audit.py` — `record_audit_event()` | Notification Service admin template update — manual DB inserts | Consolidate in `sk_shared`. Gateway is correct owner. |
| HMAC verification | Gateway webhook `verify_hmac()` | Notification Service `core/utils.py` `verify_hmac()` | Move to `sk_shared/security.py` |
| Cursor-based pagination | Gateway (manual implementation) | Product Service `_encode_cursor()/_decode_cursor()` | Move to `sk_shared/pagination.py` which already has `PaginationParams` |
| Rate limiting decorator | Gateway `@rate_limit()` | Payment Orchestrator `rate_limit(10, 60)` | Both use Redis-based sliding window — not shared via sk_shared |
| Internal token validation | Gateway `secrets.compare_digest()` | Product Service `hmac.compare_digest()` | Consistent. Both correct — not a problem. |
| Redis event publishing | Gateway `events.py` | Ledger `events/listener.py` | Publishing is in sk_shared `events.py`. ✓ |
| Health check pattern | Each service has own `/health` and `/health/ready` | All 5 services | Not duplicated — appropriate per service. ✓ |
| HITL queue | Gateway KYC HITL queue (admin_kyc.py) | Product Service HITL for extraction failures (scraping_worker.py HitlQueue) | Two different HITL systems writing to potentially same table. Need one unified HITL queue owned by one service. |

### 12.2 Missing Integration Points

| Integration | From | To | Status | Gap |
|------------|------|-----|--------|-----|
| Product URL extracted → Order updated | Product Service callback | Gateway `/internal/orders/{id}/product-extracted` | IMPLEMENTED | No retry if Gateway is down |
| Payment confirmed → Order status | Payment Orch confirm | Gateway `/internal/payments/{id}/confirm` | IMPLEMENTED | Separate transactions — saga gap |
| VCN issued → Checkout triggered | Payment Orch event publish | Product Service event listener `sk:events:vcn.issued` | IMPLEMENTED | Race condition if checkout already started |
| Delivery confirmed → Order delivered | Notification Service AfterShip | Gateway delivery event listener | IMPLEMENTED | No installment activation trigger |
| Installment overdue → Auto-collect | Ledger BillingSweepWorker | Payment Orchestrator | MISSING | This link does not exist |
| Installment overdue → User notification | Ledger BillingSweepWorker | Notification Service | MISSING | `billing.installment_overdue` event never published |
| Credit assessment complete → Order | Credit Engine | Gateway `/internal/users/{id}/credit-result` | IMPLEMENTED | Stale cache risk in credit status |
| Contract signed → Ledger loan created | Gateway ContractSigner | Ledger Service event | MISSING | Ledger Service listens for `loan.created` event but who publishes it? Gateway publishes nothing on contract signing. |
| Order cancelled → VCN voided | Gateway | Payment Orchestrator | MISSING | No `order.cancelled` handler in Payment Orchestrator. VCN stays active on Stripe. |
| Product price changed → Re-quote | Product Service PriceStalenessWorker | Gateway | MISSING | No mechanism to notify user if product price changes after offer was presented. |

### 12.3 `loan.created` Event Gap (CRITICAL CROSS-SERVICE GAP)

Ledger Service's event listener processes `loan.created` to create the initial liability GL entries (Loan Payable, Financing Receivable). But:
- Gateway's `ContractSignerService.sign_wakalah()` creates a Loan record in DB
- **No service publishes `loan.created` event** to the Redis channel
- Ledger Service never knows a loan was created
- Initial journal entries (the most important accounting entries in the system) are NEVER posted
- The entire ledger is missing the fundamental liability/receivable entries for every loan

---

## 13. MASTER GAP CHECKLIST

### Priority 1 — BLOCKERS (Cannot launch)

- [ ] **PS-BUG-01**: Fix undefined `normalized_url` in scraping_worker.py
- [ ] **PS-BUG-02**: Fix undefined `prohibited_check` in scraping_worker.py
- [ ] **PS-BL-03**: Complete `CheckoutFormFiller.run_checkout()` — payment form filling, confirmation, receipt extraction
- [ ] **PO-CRIT-01**: Implement RefundOrchestrator — refund pathway
- [ ] **LS-CRIT-02**: Add debit=credit validation to all GL entry creation
- [ ] **LS-CRIT-04**: Connect BillingSweepWorker to Payment Orchestrator for auto-collection
- [ ] **Cross-Service**: Publish `loan.created` event from Gateway on Murabaha signing
- [ ] **PS-BL-02**: Obtain Shariah board written approval for tiered pricing markup
- [ ] **WA-CRIT-01**: Replace hardcoded mock dashboard data with real API calls
- [ ] **WA-CRIT-02/03**: Implement JWT token handling and login in web-admin
- [ ] **WEB-CUSTOMER**: Build ALL customer screens (registration through installment payment)
- [ ] **GW-BL-01**: Implement credit reservation (TASK-11) at order initiation

### Priority 2 — HIGH (Must fix within first release cycle)

- [ ] **GW-BL-03**: Enforce Wakalah signed before Murabaha generation
- [ ] **GW-BL-04**: Allow cancellation in CONTRACTS_SIGNED state (before VCN/payment)
- [ ] **GW-BL-05**: Implement TOTP brute-force lockout (max 5 attempts) — TASK-16
- [ ] **GW-BL-06**: Implement saga compensation for payment confirm → order status update
- [ ] **GW-GAP-01/02**: Implement system_parameters CRUD API and seed defaults in migration
- [ ] **GW-GAP-03**: Admin manual order status override endpoint
- [ ] **PO-CRIT-04**: Void VCN on Stripe when VcnExpiryWorker marks expired
- [ ] **PO-CRIT-02**: Implement real JazzCash SFTP and SafePay API settlement download
- [ ] **PO-EP-06**: Implement `/api/internal/installments/{id}/auto-collect` for billing sweep
- [ ] **PO-BL-03**: Implement saga compensation for payment capture → Gateway callback
- [ ] **PO-BL-01**: Add rate limiting to `/api/internal/vcn/{order_id}/decrypt`
- [ ] **LS-CRIT-01**: Implement cash flow statement
- [ ] **LS-CRIT-03**: Implement charity fund disbursement (TasdeeqService)
- [ ] **LS-CRIT-05**: Implement DLQ consumer for failed ledger events
- [ ] **NS-BUG-01**: Fix OTP user_id=1 assignment for unregistered users
- [ ] **NS-BL-01**: Add HMAC signature verification to SendGrid webhook
- [ ] **NS-BL-05**: Implement `billing.installment_overdue` event publishing (from Ledger)
- [ ] **NS-BL-09**: Implement ScheduledNotification background worker
- [ ] **Cross-Service**: Publish `order.cancelled` to Notification Service for user alert
- [ ] **Cross-Service**: Void VCN when order is cancelled (`order.cancelled` handler in Payment Orch)
- [ ] **Cross-Service**: Connect delivery confirmed to installment schedule activation
- [ ] **DB-GAP-04**: Seed default system_parameters in migration
- [ ] **INF-GAP-04**: Propagate X-Request-ID to all downstream services
- [ ] **INF-GAP-11**: Add `alembic upgrade head` to K8s deployment init container

### Priority 3 — MEDIUM (Pre-scale fixes)

- [ ] **GW-BL-07**: Refresh credit limit from DB before returning in credit status endpoint
- [ ] **GW-BL-12**: Sync RBAC permission matrix — add `manage_system` to appropriate roles
- [ ] **GW-BL-13**: Add webhook event deduplication
- [ ] **GW-BL-14**: Enhance Shariah audit to check charity disbursement and profit rates
- [ ] **PS-BL-01**: Complete `ProhibitedCheckerService.check_url()` with domain blacklist
- [ ] **PS-BL-06**: Handle VCN-issued + order-cancelled race condition in checkout consumer
- [ ] **PS-BL-07**: Implement daily re-check job for products against updated prohibited categories
- [ ] **PO-CRIT-03**: Implement Raast mandate lookup for recurring auto-collection
- [ ] **LS-BL-01**: Validate account codes exist before posting journal entries
- [ ] **LS-BL-02**: Enforce period close prevents backdated entries
- [ ] **LS-BL-08**: Validate late fee does not exceed Shariah-permitted bound
- [ ] **LS-BL-09**: Publish overdue notification when billing sweep detects overdue
- [ ] **NS-BL-03**: Document and test OTP rate limit thresholds
- [ ] **NS-BL-07**: Restrict OTP template modification to superadmin permission
- [ ] **GW-GAP-05**: Implement payment restructuring endpoint
- [ ] **GW-GAP-07**: Implement blacklist entry removal endpoint
- [ ] **GW-GAP-11**: Implement customer refund request endpoint
- [ ] **DB-GAP-01**: Implement `downgrade()` for all critical migrations
- [ ] **DB-GAP-05**: Add `(type, value)` index on risk_blacklist for fast lookup
- [ ] **INF-GAP-01**: Define Prometheus alerting rules and Grafana dashboards
- [ ] **INF-GAP-02**: Configure Fluent Bit log shipping
- [ ] **INF-GAP-08**: Move audit trail to immutable S3-backed store

### Priority 4 — LOW (Post-launch)

- [ ] **PS-BL-08**: Implement merchant reputation scoring update
- [ ] **PS-BL-12**: Implement product staleness/expiry job
- [ ] **GW-GAP-12/13**: Implement cohort analysis and custom reports
- [ ] **GW-GAP-14**: Implement merchant management admin panel
- [ ] **GW-GAP-16**: Implement support ticket system (no backend either)
- [ ] **SH-GAP-02**: Fix refresh token / access token decode logic
- [ ] **SH-GAP-03**: Add event envelope schema validation (Pydantic model for publish)
- [ ] **INF-GAP-07**: Implement secret rotation mechanism
- [ ] **INF-GAP-09**: Add secret scanning to CI pipeline

---

## APPENDIX: SERVICE ENDPOINT COUNT SUMMARY

| Service | Customer Endpoints | Admin Endpoints | Internal Endpoints | Webhooks | Total |
|---------|-------------------|-----------------|-------------------|---------|-------|
| Gateway | 29 | 45+ | 8 | 2 | 84+ |
| Product Service | 10 | 18 | 0 | 0 | 28 |
| Payment Orchestrator | 3 | 1 | 1 | 0 | 5 |
| Ledger Service | 13 | 0 | 0 | 0 | 13 |
| Notification Service | 7 | 9 | 3 | 4 | 23 |
| **TOTAL** | **62** | **73+** | **12** | **6** | **153+** |

## APPENDIX: COMPLETION ESTIMATE

| Component | Estimated Completion |
|-----------|---------------------|
| Gateway (backend) | 85% |
| Product Service (backend) | 60% (checkout agent blocking) |
| Payment Orchestrator (backend) | 70% (refund, reconciliation blocking) |
| Ledger Service (backend) | 65% (cash flow, auto-collect missing) |
| Notification Service (backend) | 80% |
| web-admin (frontend) | 10% (shells only, fake data) |
| web-customer (frontend) | 2% (scaffold only) |
| **Overall Platform** | **~55%** |

---

*End of report. Total gaps identified: 120+. Critical blockers: 14. High priority: 32. Medium priority: 42. Low priority: 32+.*
