# Gateway Microservice — Complete Engineering Reference & Production Audit

**Service path:** `apps/gateway/`  
**Audit date:** 2026-04-27, corrected and re-verified 2026-08-28  
**Status:** ⚠️ Functionally complete, was NOT zero-gaps as previously claimed — see [§11](#11-bug--gap-resolution-log). A rigorous 2026-08 cross-service audit (`docs/PRODUCTION_GAPS_REPORT_2026-08.md`) found real CRITICAL/HIGH bugs in Gateway specifically. All Gateway-specific CRITICAL findings and the Gateway-specific HIGH findings listed in that report have since been verified fixed by direct reading of the current code (not just trusting the report) — see §11 for the itemized disposition. Zero cross-service/E2E test coverage was the deeper finding; a first real E2E test now exists (see end of §1).  

---

## Table of Contents

1. [Service Purpose & Role in the System](#1-service-purpose--role-in-the-system)
2. [Architecture Overview](#2-architecture-overview)
3. [Request Lifecycle (Incoming Flow)](#3-request-lifecycle-incoming-flow)
4. [Outgoing Flows (Emitted Events & Queues)](#4-outgoing-flows-emitted-events--queues)
5. [Complete File Registry](#5-complete-file-registry)
6. [API Endpoint Catalog](#6-api-endpoint-catalog)
7. [Order State Machine](#7-order-state-machine)
8. [Security Controls Matrix](#8-security-controls-matrix)
9. [Data Storage & Caching Strategy](#9-data-storage--caching-strategy)
10. [RBAC Permission Matrix](#10-rbac-permission-matrix)
11. [Bug & Gap Resolution Log](#11-bug--gap-resolution-log)
12. [Test Coverage](#12-test-coverage)
13. [Deployment Checklist](#13-deployment-checklist)

---

## 1. Service Purpose & Role in the System

The **Gateway** is the single HTTP entry point for all external and inter-service traffic in the SahulatKar platform. It owns:

- **Customer identity** — phone-OTP registration, password login, JWT session management, GDPR/PECA-compliant account deletion
- **Shariah-compliant order lifecycle** — URL submission → product extraction → financing offer → contract generation/signing → payment orchestration
- **Admin back-office** — RBAC-enforced management of users, KYC, orders, payments, compliance, risk, and system configuration
- **Inbound webhooks** — payment confirmation from JazzCash, SafePay, Stripe with HMAC-SHA256 verification
- **Internal callbacks** — typed endpoints for Product Service, Payment Orchestrator, Credit Engine, and Notification Service to push results back
- **Delivery tracking** — async Redis pub/sub listener that applies shipment and delivery events to order records

No other microservice exposes external HTTP endpoints. All downstream services receive work via Redis queues or direct HTTP calls signed with `INTERNAL_SERVICE_TOKEN`.

**For a new frontend team:** a real cross-service end-to-end test now exists at `tests/e2e/test_order_lifecycle.py` (with `tests/e2e/conftest.py`), exercising the full order lifecycle through this Gateway — order creation → extraction → offer → Wakalah/Murabaha signing → down payment → VCN issuance → delivery — against real (not mocked) sibling services. Local full-stack development and testing is done via `docker compose` (see `infra/docker/docker-compose.yml`, which brings up all 6 services + Postgres + Redis + PgBouncer). Running that E2E suite against a live `docker compose up` stack is the most reliable way for a new frontend's AI coding agent to see exact request/response shapes for every step of the order flow, rather than relying solely on this document.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        EXTERNAL TRAFFIC                             │
│   Mobile App / Admin Panel / Payment Gateways / Internal Services   │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ HTTPS
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      GATEWAY  (apps/gateway)                        │
│                                                                     │
│  Middleware Stack (in order):                                       │
│  1. SecurityHeadersMiddleware  — IP allowlist, origin check         │
│  2. RequestIDMiddleware        — X-Request-ID, X-Process-Time       │
│  3. CORSMiddleware             — app.sahulatkar.pk + admin domain   │
│  4. apply_rate_limit (http)    — global + per-user + per-admin      │
│                                                                     │
│  FastAPI Router (/api/v1/*)                                         │
│  ├── Customer APIs  (auth, kyc, orders, payments, contracts, ...)   │
│  ├── Admin APIs     (dashboard, users, kyc, orders, compliance ...) │
│  ├── Webhooks       (jazzcash, safepay, stripe)                     │
│  └── Internal       (callbacks from other microservices)            │
│                                                                     │
│  Background Tasks:                                                  │
│  ├── delivery_event_listener  — Redis pub/sub subscriber            │
│  └── listener_watchdog        — restarts listener on crash          │
└──────┬──────────────────────────────────────────┬───────────────────┘
       │ PostgreSQL (async SQLAlchemy)             │ Redis
       ▼                                           ▼
┌─────────────┐   ┌──────────────────────────────────────────────────┐
│  Primary DB │   │  Redis Roles                                     │
│             │   │  • Session store (sk:auth:session:*)             │
│  All models │   │  • Rate limit tracking (sorted sets)             │
│  Soft-delete│   │  • OTP / token store (sk:auth:otp:*, token:*)   │
│  Audit trail│   │  • Work queues (PRODUCT_EXTRACT, PAYMENT_INIT,  │
│  Contracts  │   │    VCN_ISSUE, PAYMENT_WEBHOOK, NOTIFICATION_SMS) │
│  KYC records│   │  • Pub/sub channels (delivery events, loan.created) │
└─────────────┘   │  • Idempotency keys (webhooks, down-payments)   │
                  │  • Audit DLQ (sk:audit:dlq)                     │
                  │  • Dashboard KPI cache                           │
                  └──────────────────────────────────────────────────┘
```

---

## 3. Request Lifecycle (Incoming Flow)

### 3.1 Customer Request

```
Client → HTTPS → SecurityHeadersMiddleware
              → RequestIDMiddleware (assigns X-Request-ID)
              → CORSMiddleware
              → rate_limit_middleware
                   ├── Global: 100 req/min per IP
                   ├── Auth endpoints: 10 req/min per IP
                   └── Per-user: 60 req/min (from JWT claim)
              → FastAPI Router
              → Depends(get_current_user)
                   ├── Decode JWT (RS256, public key)
                   ├── Check sk:auth:session:{sha256(token)} in Redis
                   ├── Fallback: check UserSession table in DB
                   ├── Verify user.deleted_at IS NULL
                   ├── Check user.locked_until
                   └── Check user.status not in [suspended, blocked]
              → Route handler → Service → DB commit → Response
```

### 3.2 Admin Request

```
Client → same middleware stack
       → Depends(get_current_admin)
            ├── Decode JWT, assert token_type == "admin"
            ├── Check sk:auth:admin_session:{sha256(token)} in Redis
            └── Fetch AdminUser from DB
       → Depends(RequirePermission("some_permission"))
            └── Check payload.permissions list (embedded in JWT)
       → Route handler → Service → record_audit_event → DB commit
```

### 3.3 Webhook Request (Payment Gateway)

```
Payment Gateway → POST /api/v1/webhooks/payment/{provider}
                → _enforce_json_content_type()         (SEC-04)
                → body = await request.body()
                → _enforce_payload_size(body)           (1 MB limit)
                → _verify_signature(secret, body, header) (HMAC-SHA256)
                → idempotency check in Redis (sk:webhook:processed:*)
                → redis.lpush(PAYMENT_WEBHOOK, payload)
                → return {"received": True}
```

### 3.4 Internal Service Callback

```
Microservice → POST /api/v1/internal/{endpoint}
             → _require_internal(request)
                  ├── secrets.compare_digest(token, INTERNAL_SERVICE_TOKEN)
                  └── enforce Content-Type: application/json  (SEC-03)
             → typed Pydantic payload validation
             → DB mutation + optional Redis event publish
             → return {"status": "ok"}
```

---

## 4. Outgoing Flows (Emitted Events & Queues)

| Trigger | Channel / Queue | Consumer |
|---|---|---|
| `POST /orders/initiate` | Redis `PRODUCT_EXTRACT` queue + HTTP nudge to Product Service | Product Service |
| `POST /payments/down-payment` | Redis `PAYMENT_INITIATE` queue | Payment Orchestrator |
| `POST /payments/installment/*/pay` | Redis `PAYMENT_INITIATE` queue | Payment Orchestrator |
| `POST /payments/vcn/issue` | Redis `VCN_ISSUE` queue | Payment Orchestrator |
| `POST /payments/refund/{order_id}` | Redis `PAYMENT_INITIATE` queue | Payment Orchestrator |
| `POST /orders/{id}/cancel` | Redis `NOTIFICATION_SMS` queue + pub/sub `ORDER_CANCELLED` | Notification Service + Payment Orchestrator |
| Murabaha sign success | Redis pub/sub `loan.created` | Ledger Service |
| Webhooks (any provider) | Redis `PAYMENT_WEBHOOK` queue | Payment Orchestrator |
| Any admin action | `AuditTrail` DB record (+ Redis DLQ on failure) | — |

---

## 5. Complete File Registry

### 5.1 Entry Point & Configuration

| File | Purpose |
|---|---|
| `src/main.py` | FastAPI app factory. Runs `validate_critical_settings()` at startup (aborts on misconfiguration in production). Starts Redis connection pool, `delivery_event_listener` (pub/sub), `listener_watchdog` (auto-restart on crash), and `InternalServiceClient` HTTP pool. Registers all middleware and the main router. Exposes `GET /health` (DB + Redis + listener). |
| `src/config.py` | `pydantic-settings` `BaseSettings`. All config from environment variables with `.env` fallback. Contains `validate_critical_settings()` which checks KMS key, internal token, webhook secrets, S3 bucket, SECP license, and JWT private key when `ENVIRONMENT=production`. |
| `src/api/routes.py` | Single `APIRouter` that imports and mounts all 36 sub-router objects (35 files under `src/api/v1/` — `admin_compliance.py` defines two: `router` and a separate `audit_router`) under `/api/v1/`. Also exposes `GET /api/v1/health-check`. |

### 5.2 Core Infrastructure

| File | Purpose |
|---|---|
| `src/core/middleware.py` | Two `BaseHTTPMiddleware` subclasses. **`RequestIDMiddleware`**: reads/generates `X-Request-ID`, populates correlation context var, adds `X-Process-Time` to response. **`SecurityHeadersMiddleware`**: enforces admin IP allowlist (SEC-02), admin origin check (SEC-07), and attaches HSTS/CSP/X-Frame-Options/X-Content-Type-Options to all non-docs responses. |
| `src/core/rate_limit.py` | Sliding-window rate limiter backed by Redis sorted sets. Limits: global 100/min per IP, auth endpoints 10/min per IP, per-user 60/min, per-admin configurable (default 30/min). Health and internal endpoints bypassed. Test environment bypassed unless `X-Test-Rate-Limit` header present. |
| `src/core/dependencies.py` | FastAPI `Depends()` providers: `get_db` (async SQLAlchemy session), `get_redis` (from `app.state.redis`), `get_current_user` (JWT → Redis session → DB user → lockout check), `get_current_admin` (JWT → Redis admin session → DB admin), `get_admin_for_password_change` (accepts both regular and temp tokens), `RequireRole([...])`, `RequirePermission("...")`, `rate_limit_auth` (per-IP auth rate limiter). |
| `src/core/audit.py` | `record_audit_event()` — adds an `AuditTrail` row to the current DB session. On failure writes to Redis DLQ (`sk:audit:dlq`) so compliance records are never silently dropped. Caller must call `db.commit()` separately. |
| `src/core/kms.py` | `KMSProvider` class with `encrypt(plaintext)` / `decrypt(ciphertext)` methods. Local mode: AES-256-GCM with `KMS_MOCK_KEY_HEX`. Production mode: AWS KMS Boto3 path when `KMS_KEY_ARN` is set. Used for CNIC storage in `CustomerProfile` and MFA secret storage in `AdminUser`. |
| `src/core/logging.py` | Structured JSON logging setup (`setup_logging()`). Exports a module-level `logger`. Used throughout the codebase. JSON format targets K8s/CloudWatch log aggregation. |
| `src/core/metrics.py` | `setup_metrics(app)` — wires Prometheus instrumentation. Exposes `/metrics` endpoint. Tracks request count, latency histograms by endpoint. |
| `src/core/http_client.py` | `InternalServiceClient` — singleton `httpx.AsyncClient` with connection pooling. `start()` / `stop()` called in lifespan. `signed_headers(request_id)` adds `X-Internal-Token` + correlation ID for outbound calls to Product Service. |

### 5.3 Customer API Layer (`src/api/v1/`)

| File | Prefix | Key Endpoints |
|---|---|---|
| `auth.py` | `/auth` | `POST /register/initiate`, `POST /verify-otp`, `POST /login`, `POST /logout`, `POST /refresh`, `GET /me`, `POST /forgot-password`, `POST /reset-password`, `GET /sessions`, `DELETE /sessions/{id}`, `DELETE /sessions`, `POST /devices/register`, `DELETE /devices/{id}`, `DELETE /account` |
| `kyc.py` | `/kyc` | `POST /start`, `POST /upload/{document_type}`, `POST /submit`, `GET /status`, `POST /resubmit`, `PUT /profile`, `GET /profile` |
| `orders.py` | `/orders` | `POST /initiate`, `GET /{id}/offer`, `POST /{id}/accept`, `GET` (list), `GET /{id}`, `GET /{id}/tracking`, `POST /{id}/cancel`, `GET /{id}/receipt` |
| `payments.py` | `/payments` | `POST /down-payment`, `POST /vcn/issue`, `GET /vcn/status/{order_id}`, `GET /schedule/{order_id}`, `POST /installment/{id}/pay`, `POST /installment/pay` (legacy), `POST /installment/retry`, `POST /refund/{order_id}` |
| `contracts.py` | `/contracts` | `POST /wakalah/generate`, `POST /wakalah/sign`, `POST /murabaha/generate`, `POST /murabaha/sign`, `GET /{order_id}` (status), `GET /{type}/{id}/download`, `GET /{type}/{id}/verify` |
| `credit.py` | `/credit` | `GET /status`, `GET /history` |
| `profile.py` | `/profile` | `GET /notifications`, `PUT /notifications`, `GET /referrals` |
| `cart.py` | `/cart` | `POST /items` (add product URL, kicks off extraction+offer like `orders.py`), `GET` (list), `DELETE /items/{id}`, `POST /checkout` (converts cart into orders under one installment plan) — backed by `services/cart_service.py` |
| `support.py` | `/support` | `POST /tickets`, `GET /tickets`, `GET /tickets/{id}`, `POST /tickets/{id}/messages` — customer-facing support ticket CRUD over raw-SQL `support_tickets`/`ticket_messages` tables; a reply on a resolved/waiting ticket reopens it |
| `notifications.py` | `/notifications` | `GET` (paginated, `unread_only` filter), `POST /{id}/read`, `POST /read-all` — customer in-app notification inbox (separate from `admin_notifications.py`'s admin-side template/broadcast console) |
| `webhooks.py` | `/webhooks` | `POST /payment/jazzcash`, `POST /payment/safepay`, `POST /payment/stripe` |
| `internal.py` | `/internal` | `POST /orders/{id}/product-extracted`, `POST /orders/{id}/extraction-failed`, `POST /payments/{id}/confirm`, `POST /users/{id}/credit-result`, `POST /credit/update-result`, `POST /orders/{id}/shipment-registered`, `POST /shipment/register`, `POST /orders/{id}/checkout-status` |

### 5.4 Admin API Layer (`src/api/v1/`)

| File | Prefix | Key Endpoints & Permissions Required |
|---|---|---|
| `admin_auth.py` | `/admin/auth` | `POST /login` (IP-allowlisted), `GET /me`, `POST /logout`, `POST /mfa/setup`, `POST /mfa/verify`, `POST /admins` (`manage_admins`), `PUT /admins/{id}/role` (`manage_admins`), `POST /change-password`, `GET /roles` (`manage_admins`) |
| `admin_dashboard.py` | `/admin/dashboard` | `GET /summary` — KPI cards (GMV, active orders, KYC queue, default rate). Redis-cached with TTL `ADMIN_DASHBOARD_CACHE_TTL`. |
| `admin_analytics.py` | `/admin/analytics` | `GET /revenue`, `GET /user-growth`, `GET /product-performance` (`read_analytics`) |
| `admin_kyc.py` | `/admin/kyc` | `GET /queue`, `GET /queue/{id}`, `POST /queue/{id}/claim`, `POST /queue/{id}/approve`, `POST /queue/{id}/reject` (`manage_kyc_queue`) |
| `admin_hitl.py` | `/admin/hitl` | `GET /queue`, `GET /queue/{id}`, `POST /queue/{id}/claim`, `POST /queue/{id}/resolve`, `POST /queue/{id}/escalate` |
| `admin_orders.py` | `/admin/orders` | Much larger than originally documented. `GET ""` (paginated/filtered list, `read_order`), `GET /summary`, `GET /{id}`, `PUT /{id}/status` (validated against `OrderState`, `manage_orders`), `GET /{id}/installments`, `GET /{id}/payments` (`manage_payments`), `GET /{id}/timeline`, `GET /{id}/vcn`, `POST /{id}/retry-vcn` (HIGH-2 fix — re-queues a stuck `pending_vcn` order's VCN issuance job; previously only a read-only view existed), `POST /{id}/refund`, `POST /{id}/restructure`, `POST ""` (manual order creation, `manage_orders`), `GET /{id}/communications`. List/detail queries were fixed to stop swallowing real SQL errors as empty results/404s (see §11 CRITICAL-11 disposition) |
| `admin_payments.py` | `/admin/payments` | `GET /transactions`, `GET /transactions/{id}`, `POST /refund/{order_id}` (`manage_payments`) |
| `admin_installments.py` | `/admin/installments` | `GET /`, `GET /{id}`, `POST /{id}/waive-fee`, `POST /{id}/mark-paid` (`manage_payments`) |
| `admin_users.py` | `/admin/users` | `GET /` (search by ID/phone), `GET /{id}`, `PUT /{id}/status`, `POST /{id}/blacklist`, `PUT /{id}/credit-limit`, `DELETE /{id}` (`manage_users`) |
| `admin_risk.py` | `/admin/risk` | `GET /blacklist`, `POST /blacklist`, `DELETE /blacklist/{id}` (`manage_risk`) |
| `admin_approvals.py` | `/admin/approval-requests` | Generic manager-approval workflow shared by credit-limit-increase and loan-restructuring flows. `GET ""`, `GET /{id}`, `POST /{id}/decision` (approve/reject; rejects self-approval; `approved` + `credit_limit_increase` auto-applies the new limit) — all `manage_users` |
| `admin_finance.py` | `/admin/finance` | `GET /pnl` (monthly GMV/profit/cost series), `GET /credit-loss` (defaulted/written-off exposure + provision estimate, reads `credit_loss_provision_rate_pct` from `admin_system`), `GET /tax-summary` (GST liability, reads `gst_rate_pct`), `POST /tax-summary/generate` (`manage_financials`, snapshots an FBR GST-return filing row) — all `read_financials` unless noted |
| `admin_notifications.py` | `/admin/notifications` | Admin-side notification console (distinct from customer-facing `notifications.py`). `GET ""`, `GET /summary`, `GET /templates`, `POST /templates`, `PUT /templates/{id}` (`manage_system`), `POST /broadcast` (segmented push to `all_active`/`pending_kyc`/specific user IDs, max 5000 recipients, `manage_system`) — reads default `read_reports` |
| `admin_documents.py` | `/admin/documents` | Admin-side complement to the KYC queue for raw `user_documents` rows. `GET ""`, `GET /{id}`, `POST /{id}/decision` (verified/rejected), `GET /summary/counts` — all `manage_kyc_queue` |
| `admin_logs.py` | `/admin/logs` | Standalone operational log viewer (not compliance-scoped, unlike `admin_compliance.py`). `GET /errors`, `GET /background-jobs`, `GET /scheduled-tasks`, `GET /summary` — all `read_reports` |
| `admin_reports.py` | `/admin/reports` | Wraps the `regulatory_reports` table populated by `admin_finance.py`'s tax-filing endpoint. `GET ""` (filterable by `report_type`), `GET /summary` — `read_reports` |
| `admin_developer.py` | `/admin/developer` | Partner/merchant API integration management. `GET /api-keys`, `POST /api-keys` (returns the raw key once, `manage_system`), `DELETE /api-keys/{id}`, `GET /webhooks`, `GET /integration-logs`, `GET /summary` — all `manage_system` |
| `admin_marketing.py` | `/admin/marketing` | `GET /campaigns`, `POST /campaigns` (`manage_system`), `GET /promo-codes`, `POST /promo-codes` (`manage_system`), `GET /referrals/summary`, `GET /ab-tests` — reads default `read_marketing` |
| `admin_system.py` | `/admin/system` | `GET /parameters`, `PUT /parameters` (bulk), `PUT /parameters/{key}` (single), `GET /integrations`, `PUT /integrations/{id}`, `GET /health` — all `manage_system`. Parameters are Redis-cached (version-bumped invalidation) and are now genuinely read by business logic — `OrderService.initiate()` reads `max_active_orders`, `ContractGeneratorService` reads `wakalah_validity_days`/`murabaha_validity_days`/`profit_rate_{3,4,6,12}m`, `admin_finance.py` reads `credit_loss_provision_rate_pct`/`gst_rate_pct` — via `src/services/system_parameters.py:get_effective_system_parameters()`. See §11 CRITICAL-12 disposition — this used to be a facade with zero effect on live contracts. |
| `admin_compliance.py` | `/admin/compliance` | `GET /audit-trail`, `GET /shariah-audit`, `GET /shariah-board-approvals`, `POST /shariah-board-approvals` (`manage_compliance` — records a real, admin-attested Shariah board sign-off per contract `template_version`; backs `MurabahaContract.validated_by_shariah_board`, see §11 HIGH disposition) — `read_compliance` unless noted, plus separate `audit_router` for `GET /admin/audit-trail` |
| `admin_admins.py` | `/admin/admins` | `GET /` (list admins), `GET /{id}`, `DELETE /{id}` (`manage_admins`) |
| `admin_partners.py` | `/admin/partners` | `GET /`, `GET /{id}` (`read_partners`) |
| `admin_support.py` | `/admin/support` | `GET /tickets`, `GET /tickets/{id}`, `POST /tickets/{id}/resolve` (`read_support`) |

### 5.5 Services (`src/services/`)

| File | Purpose |
|---|---|
| `auth.py` | `AuthService` (static methods). All auth business logic: OTP registration flow, OTP verification, phone/password login, admin login (password + TOTP + `force_password_change` temp-token flow), token refresh, forgot-password, reset-password, logout. Handles lockout (5 failed attempts → 30-min ban), session creation in DB + Redis. |
| `order_service.py` | `OrderService`. `initiate()`: KYC check, credit check, prohibited-URL check (tobacco/alcohol/gambling), max-active-orders check (5), creates `Order` row, pushes to `PRODUCT_EXTRACT` queue + HTTP nudge to Product Service. `get_offer()`: returns offer or pending/failed status with 10-min extraction timeout. `accept_offer()`: atomic `UPDATE ... WHERE status=offer_presented RETURNING id` to prevent race conditions. |
| `kyc.py` | `KycService`. `get_or_create_kyc()`, `upload_document()`, `submit_for_verification()` (runs Shufti OCR + liveness, then NADRA CNIC check, then queues for manual review if all pass), `get_profile()` (decrypts KMS-encrypted CNIC), `upsert_profile()` (KMS-encrypts CNIC before save). |
| `contract_generator.py` | `ContractGeneratorService`. `generate_wakalah()`: creates `WakalahAgreement`, generates PDF via ReportLab, stores in S3/local, issues OTP for signing. `generate_murabaha()`: validates Wakalah is signed, creates `MurabahaContract` with installment schedule, generates PDF, issues OTP. Includes Murabaha validity guard (BUG-06). |
| `contract_signer.py` | `ContractSignerService`. `sign_wakalah()`: verifies OTP (3-attempt lockout), checks `valid_until`, marks signed, transitions order to `CONTRACTS_PENDING`, creates `ContractDigitalSignature`. `sign_murabaha()`: same OTP flow, transitions order to `CONTRACTS_SIGNED`, **auto-creates `Loan` + `Installment` schedule**, publishes `loan.created` event to Ledger Service. |
| `rbac.py` | `RBACService`. Static role→permissions mapping for 12 roles: `super_admin`, `risk_officer`, `kyc_reviewer`, `analyst`, `support`, `operations_manager`, `credit_risk_analyst`, `fraud_analyst`, `cs_agent`, `finance_analyst`, `compliance_officer`, `marketing_manager`. `has_permission()` checks for `all_actions` wildcard first. |
| `delivery_events.py` | Event handlers called by `delivery_event_listener` in `main.py`. `apply_delivery_status_envelope()`: updates `Shipment.status` and creates `TrackingEvent`. `apply_delivery_confirmed_envelope()`: transitions order to `DELIVERED`. |
| `hitl_queue.py` | HITL (Human-In-The-Loop) queue service. Claim, resolve, and escalate `HitlQueue` entries created when checkout fails. |
| `kyc_queue.py` | KYC queue management service. Claim, approve, reject `KycVerificationQueue` entries. Approve transitions `UserKycVerification` status to `APPROVED` and user status to `active`. |
| `nadra.py` | `NadraClientMock` — mock NADRA CNIC verification client. Returns success for test CNICs. In production, replace with real NADRA API client. |
| `shufti.py` | `ShuftiClientMock` — mock Shufti OCR/liveness client. Returns success with extracted CNIC data. In production, replace with real Shufti API client. |

### 5.6 Schemas (`src/schemas/`)

| File | Pydantic models defined |
|---|---|
| `auth.py` | `RegisterInitiateRequest/Response`, `VerifyOtpRequest`, `AuthResponse`, `LoginRequest`, `TokenRefreshRequest/Response`, `CurrentUserResponse`, `ResendOtpRequest`, `AdminLoginRequest` (→ `admin_auth.py`), `AdminMfaSetupResponse`, `AdminMfaVerifyRequest`, `AdminAuthResponse` |
| `kyc.py` | `CustomerProfileBase`, `CustomerProfileResponse`, `KycVerificationResponse` |
| `orders.py` | `OrderInitiateRequest/Response`, `OrderOfferResponse`, `OrderAcceptRequest`, `OrderSummary`, `OrderDetailResponse` |
| `payments.py` | `DownPaymentRequest/Response`, `InstallmentDetail`, `PaymentScheduleResponse`, `VcnIssueRequest/Response` |
| `contracts.py` | `WakalahGenerateRequest/Response`, `WakalahSignRequest`, `MurabahaGenerateRequest/Response`, `MurabahaSignRequest`, `ContractSignResponse`, `ContractStatusResponse`, `ContractDisclosure`, `AdminContractResponse` |
| `admin_auth.py` | `AdminLoginRequest`, `AdminLoginResponse`, `AssignRoleRequest`, `CreateAdminRequest` |
| `hitl.py` | HITL queue request/response schemas |

### 5.7 Tests (`tests/`)

The suite has grown to 34 test files (up from the 7 originally listed here) — see [§12 Test Coverage](#12-test-coverage) for the current, complete file list, what each covers, and real pass/fail numbers from actually running the suite, rather than duplicating a now-stale subset here.

---

## 6. API Endpoint Catalog

### 6.1 Customer Endpoints

```
POST   /api/v1/auth/register/initiate       — Start phone registration, returns otp_token
POST   /api/v1/auth/verify-otp              — Verify OTP, creates user + session
POST   /api/v1/auth/login                   — Password or OTP login
POST   /api/v1/auth/logout                  — Revoke current session
POST   /api/v1/auth/refresh                 — Rotate access token using refresh token
GET    /api/v1/auth/me                      — Current user profile
POST   /api/v1/auth/otp/resend              — Resend OTP (max 3 per hour)
POST   /api/v1/auth/forgot-password         — Initiate password reset (anti-enumeration)
POST   /api/v1/auth/reset-password          — Complete password reset with OTP
GET    /api/v1/auth/sessions                — List active sessions
DELETE /api/v1/auth/sessions/{id}           — Revoke specific session
DELETE /api/v1/auth/sessions               — Revoke all sessions
POST   /api/v1/auth/devices/register        — Register device push token
DELETE /api/v1/auth/devices/{id}            — Deregister device
DELETE /api/v1/auth/account                 — GDPR/PECA account deletion (PII anonymised)

POST   /api/v1/kyc/start                    — Initialise KYC record (idempotent)
POST   /api/v1/kyc/upload/{document_type}   — Upload cnic_front | cnic_back | liveness_video
POST   /api/v1/kyc/submit                   — Run Shufti OCR + NADRA check + queue for review
GET    /api/v1/kyc/status                   — Get KYC status + presigned document URLs
POST   /api/v1/kyc/resubmit                 — Reset rejected KYC for re-attempt (max 3)
PUT    /api/v1/kyc/profile                  — Create/update customer profile (CNIC KMS-encrypted)
GET    /api/v1/kyc/profile                  — Get customer profile

POST   /api/v1/orders/initiate              — Submit product URL (KYC + credit + prohibited-URL checks)
GET    /api/v1/orders/{id}/offer            — Poll for financing offer (10-min extraction timeout)
POST   /api/v1/orders/{id}/accept           — Accept offer with installment plan (atomic transition)
GET    /api/v1/orders                       — List orders (filterable by status)
GET    /api/v1/orders/{id}                  — Order detail
GET    /api/v1/orders/{id}/tracking         — Shipment + latest tracking event
POST   /api/v1/orders/{id}/cancel           — Cancel order, restore credit, soft-delete loans
GET    /api/v1/orders/{id}/receipt          — Generate PDF receipt (ReportLab → S3/local)

POST   /api/v1/contracts/wakalah/generate   — Generate Wakalah PDF + issue signing OTP
POST   /api/v1/contracts/wakalah/sign       — Sign Wakalah with OTP
POST   /api/v1/contracts/murabaha/generate  — Generate Murabaha PDF (requires signed Wakalah)
POST   /api/v1/contracts/murabaha/sign      — Sign Murabaha; auto-creates Loan + Installments
GET    /api/v1/contracts/{order_id}         — Contract status (wakalah/murabaha signed flags)
GET    /api/v1/contracts/{type}/{id}/download — Presigned PDF download URL
GET    /api/v1/contracts/{type}/{id}/verify — SHA-256 integrity check of stored PDF

POST   /api/v1/payments/down-payment        — Initiate down payment (idempotency key support)
POST   /api/v1/payments/vcn/issue           — Request VCN (gate: requires DOWN_PAYMENT_RECEIVED)
GET    /api/v1/payments/vcn/status/{order}  — Check VCN issuance status
GET    /api/v1/payments/schedule/{order}    — Full installment schedule
POST   /api/v1/payments/installment/{id}/pay — Pay installment (amount tolerance ±1 PKR)
POST   /api/v1/payments/installment/pay      — Pay installment (legacy body form)
POST   /api/v1/payments/installment/retry   — Retry failed installment payment
POST   /api/v1/payments/refund/{order}      — Customer-initiated refund request

GET    /api/v1/credit/status                — Credit limit, available credit, risk band
GET    /api/v1/credit/history               — Credit limit change history (paginated)

GET    /api/v1/profile/notifications        — Get notification preferences
PUT    /api/v1/profile/notifications        — Update notification preferences
GET    /api/v1/profile/referrals            — Referral code + count

POST   /api/v1/cart/items                   — Add product URL to cart (kicks off extraction, like /orders/initiate)
GET    /api/v1/cart                         — List current cart + items
DELETE /api/v1/cart/items/{id}              — Remove cart item
POST   /api/v1/cart/checkout                — Convert cart into orders under one installment plan

POST   /api/v1/notifications/{id}/read      — Mark one in-app notification read
POST   /api/v1/notifications/read-all       — Mark all read
GET    /api/v1/notifications                — List in-app notifications (unread_only filter, paginated)

POST   /api/v1/support/tickets              — Create support ticket (optionally linked to order/loan)
GET    /api/v1/support/tickets              — List own tickets (category filter, paginated)
GET    /api/v1/support/tickets/{id}         — Ticket detail + message thread
POST   /api/v1/support/tickets/{id}/messages — Reply on a ticket (reopens if resolved/waiting)
```

### 6.2 Admin Endpoints

```
POST   /api/v1/admin/auth/login             — Admin login (IP-allowlisted, requires TOTP)
GET    /api/v1/admin/auth/me                — Current admin info + permissions
POST   /api/v1/admin/auth/logout            — Revoke admin session
POST   /api/v1/admin/auth/mfa/setup         — Generate TOTP secret + QR URI
POST   /api/v1/admin/auth/mfa/verify        — Verify TOTP + enable MFA (5-attempt lockout)
POST   /api/v1/admin/auth/admins            — Create admin (manage_admins)
PUT    /api/v1/admin/auth/admins/{id}/role  — Assign role + invalidate all sessions
POST   /api/v1/admin/auth/change-password   — Self-service password change
GET    /api/v1/admin/auth/roles             — List all roles + permissions

GET    /api/v1/admin/dashboard/summary      — KPI cards (Redis-cached)
GET    /api/v1/admin/analytics/revenue      — Revenue analytics
GET    /api/v1/admin/analytics/user-growth  — User growth metrics
GET    /api/v1/admin/analytics/product-performance — Product analytics

GET    /api/v1/admin/kyc/queue              — KYC review queue (manage_kyc_queue)
GET    /api/v1/admin/kyc/queue/{id}         — KYC entry detail
POST   /api/v1/admin/kyc/queue/{id}/claim   — Claim KYC entry for review
POST   /api/v1/admin/kyc/queue/{id}/approve — Approve KYC → user.status = active
POST   /api/v1/admin/kyc/queue/{id}/reject  — Reject KYC with reason code

GET    /api/v1/admin/hitl/queue             — HITL checkout failure queue
GET    /api/v1/admin/hitl/queue/{id}        — HITL entry detail
POST   /api/v1/admin/hitl/queue/{id}/claim  — Claim entry
POST   /api/v1/admin/hitl/queue/{id}/resolve — Resolve entry
POST   /api/v1/admin/hitl/queue/{id}/escalate — Escalate entry

GET    /api/v1/admin/orders                 — Paginated, filtered order list (read_order)
GET    /api/v1/admin/orders/summary         — Status breakdown + GMV/avg-order-value KPIs
GET    /api/v1/admin/orders/{id}            — Order detail (incl. loan financial summary)
PUT    /api/v1/admin/orders/{id}/status     — Force status transition, validated against OrderState (manage_orders)
GET    /api/v1/admin/orders/{id}/installments — Installment schedule for the order's loan (manage_orders)
GET    /api/v1/admin/orders/{id}/payments   — Payment transaction history for the order (manage_payments)
GET    /api/v1/admin/orders/{id}/timeline   — Full order_status_history (read_order)
GET    /api/v1/admin/orders/{id}/vcn        — Virtual card issuance status (manage_orders)
POST   /api/v1/admin/orders/{id}/retry-vcn  — Re-queue VCN issuance for an order stuck at pending_vcn (manage_orders)
POST   /api/v1/admin/orders/{id}/refund     — Queue a refund for a refundable order (manage_payments)
POST   /api/v1/admin/orders/{id}/restructure — Queue a loan installment-count restructure (manage_orders)
POST   /api/v1/admin/orders                 — Manually create an order for a user (manage_orders)
GET    /api/v1/admin/orders/{id}/communications — Notifications sent to the customer about this order (read_order)

GET    /api/v1/admin/payments/transactions  — Payment transaction list
GET    /api/v1/admin/payments/transactions/{id} — Transaction detail
POST   /api/v1/admin/payments/refund/{order} — Initiate refund (manage_payments)

GET    /api/v1/admin/installments           — Installment list
GET    /api/v1/admin/installments/{id}      — Installment detail
POST   /api/v1/admin/installments/{id}/waive-fee — Waive late fee
POST   /api/v1/admin/installments/{id}/mark-paid — Force mark paid

GET    /api/v1/admin/users                  — User list (search by ID/phone)
GET    /api/v1/admin/users/{id}             — User detail
PUT    /api/v1/admin/users/{id}/status      — Suspend/unblock user
POST   /api/v1/admin/users/{id}/blacklist   — Blacklist user
PUT    /api/v1/admin/users/{id}/credit-limit — Manually set credit limit
DELETE /api/v1/admin/users/{id}             — Soft-delete admin account

GET    /api/v1/admin/risk/blacklist         — Risk blacklist entries
POST   /api/v1/admin/risk/blacklist         — Add blacklist entry (manage_risk)
DELETE /api/v1/admin/risk/blacklist/{id}    — Remove blacklist entry

GET    /api/v1/admin/system/parameters      — System parameters (Redis-cached; genuinely consumed by order/contract/finance logic — see §5.4)
PUT    /api/v1/admin/system/parameters      — Bulk update parameters (manage_system)
PUT    /api/v1/admin/system/parameters/{key} — Update a single parameter (manage_system)
GET    /api/v1/admin/system/integrations    — Third-party integration status (JazzCash, Shufti, NADRA, S3, ...)
PUT    /api/v1/admin/system/integrations/{id} — Update integration status/config (manage_system)
GET    /api/v1/admin/system/health          — DB/Redis health + queue depth + failed-job count

GET    /api/v1/admin/compliance/audit-trail — Audit trail search (read_compliance)
GET    /api/v1/admin/compliance/shariah-audit — Shariah compliance audit log
GET    /api/v1/admin/compliance/shariah-board-approvals — List recorded Shariah board template approvals
POST   /api/v1/admin/compliance/shariah-board-approvals — Record a Shariah board approval for a contract template_version (manage_compliance) — backs MurabahaContract.validated_by_shariah_board, see §11
GET    /api/v1/admin/audit-trail            — Global audit trail (separate audit_router, read_audit)

GET    /api/v1/admin/admins                 — List admin accounts (manage_admins)
GET    /api/v1/admin/admins/{id}            — Admin detail
DELETE /api/v1/admin/admins/{id}            — Delete admin

GET    /api/v1/admin/contracts/admin/wakalah   — All wakalah agreements (paginated)
GET    /api/v1/admin/contracts/admin/murabaha  — All murabaha contracts (paginated)
GET    /api/v1/admin/contracts/admin/{type}/{id}/pdf — Contract PDF download (admin)

GET    /api/v1/admin/partners               — Partner list
GET    /api/v1/admin/support/tickets        — Support tickets

GET    /api/v1/admin/approval-requests      — Pending/decided manager approval requests (credit-limit increases, restructures)
GET    /api/v1/admin/approval-requests/{id} — Approval request detail
POST   /api/v1/admin/approval-requests/{id}/decision — Approve/reject (self-approval blocked); approving credit_limit_increase applies it

GET    /api/v1/admin/finance/pnl            — Monthly GMV / platform profit / product cost series
GET    /api/v1/admin/finance/credit-loss    — Defaulted/written-off exposure + provision estimate
GET    /api/v1/admin/finance/tax-summary    — GST liability estimate for a period
POST   /api/v1/admin/finance/tax-summary/generate — Snapshot a tax summary as a regulatory filing record

GET    /api/v1/admin/notifications          — Admin view of all customer notifications
GET    /api/v1/admin/notifications/summary  — Notification status/dispatch-channel breakdown
GET    /api/v1/admin/notifications/templates — List notification templates
POST   /api/v1/admin/notifications/templates — Create template (manage_system)
PUT    /api/v1/admin/notifications/templates/{id} — Update template, bumps version (manage_system)
POST   /api/v1/admin/notifications/broadcast — Send a segmented broadcast (max 5,000 recipients, manage_system)

GET    /api/v1/admin/documents              — List uploaded user documents (KYC-adjacent)
GET    /api/v1/admin/documents/{id}         — Document detail
POST   /api/v1/admin/documents/{id}/decision — Verify/reject a document
GET    /api/v1/admin/documents/summary/counts — Document counts by status

GET    /api/v1/admin/logs/errors            — Error log search (service/severity filters)
GET    /api/v1/admin/logs/background-jobs   — Background job status
GET    /api/v1/admin/logs/scheduled-tasks   — Scheduled task (cron) status
GET    /api/v1/admin/logs/summary           — 24h error + job-status summary

GET    /api/v1/admin/reports                — Generated regulatory reports (filterable by report_type)
GET    /api/v1/admin/reports/summary        — Report counts by type + last-generated timestamp

GET    /api/v1/admin/developer/api-keys     — List partner/merchant API keys
POST   /api/v1/admin/developer/api-keys     — Issue a new API key (raw key shown once, manage_system)
DELETE /api/v1/admin/developer/api-keys/{id} — Revoke an API key
GET    /api/v1/admin/developer/webhooks     — List registered partner webhooks
GET    /api/v1/admin/developer/integration-logs — Outbound integration call log
GET    /api/v1/admin/developer/summary      — Active keys/webhooks + 24h integration success rate

GET    /api/v1/admin/marketing/campaigns    — List marketing campaigns
POST   /api/v1/admin/marketing/campaigns    — Create campaign (manage_system)
GET    /api/v1/admin/marketing/promo-codes  — List promo codes
POST   /api/v1/admin/marketing/promo-codes  — Create promo code (manage_system)
GET    /api/v1/admin/marketing/referrals/summary — Referral program status + rewards paid
GET    /api/v1/admin/marketing/ab-tests     — A/B test experiment list
```

### 6.3 Webhook Endpoints

```
POST   /api/v1/webhooks/payment/jazzcash    — JazzCash webhook (HMAC-SHA256 verified)
POST   /api/v1/webhooks/payment/safepay     — SafePay webhook (HMAC-SHA256 verified)
POST   /api/v1/webhooks/payment/stripe      — Stripe webhook (Stripe-Signature verified)
```

### 6.4 Internal Callback Endpoints

```
POST   /api/v1/internal/orders/{id}/product-extracted   — Product Service: extraction result
POST   /api/v1/internal/orders/{id}/extraction-failed   — Product Service: extraction failure
POST   /api/v1/internal/payments/{id}/confirm           — Payment Orchestrator: payment result
POST   /api/v1/internal/users/{id}/credit-result        — Credit Engine: credit assessment result
POST   /api/v1/internal/credit/update-result            — Credit Engine: bulk credit update
POST   /api/v1/internal/orders/{id}/shipment-registered — Notification Service: shipment created
POST   /api/v1/internal/shipment/register               — Notification Service: alt shipment form
POST   /api/v1/internal/orders/{id}/checkout-status     — Product Service: checkout result
```

### 6.5 System Endpoints

```
GET    /health                              — DB + Redis + listener health check (503 on failure)
GET    /api/v1/health-check                 — Simple {"status": "ok"}
GET    /metrics                             — Prometheus metrics
GET    /docs                                — Swagger UI
GET    /redoc                               — ReDoc UI
GET    /openapi.json                        — OpenAPI schema
```

---

## 7. Order State Machine

```
[User submits URL]
        │
        ▼
   url_received  ──────────────────────────────────────┐
        │ (product extracted, credit reserved)         │ (extraction fails)
        ▼                                              ▼
  offer_presented                               extraction_failed
        │ (user accepts)
        ▼
  offer_accepted
        │ (Wakalah generated + signed)
        ▼
  contracts_pending
        │ (Murabaha generated + signed → Loan + Installments created)
        ▼
  contracts_signed ←──────────────────────────────┐
        │ (down payment initiated + confirmed)     │ (payment fails: revert)
        ▼                                          │
  down_payment_received ──────────────────────────┘
        │ (VCN issued, checkout executed)
        ▼
  pending_vcn → purchase_confirmed
                        │ (shipment registered)
                        ▼
                  delivery_pending
                        │ (delivery confirmed via pub/sub)
                        ▼
                     delivered
                     
  [Any pre-payment state] ──── POST /orders/{id}/cancel ──→ cancelled
```

**Credit reservation flow:**
- Reserved at `product-extracted` callback (deducted from `user.available_credit`)
- Released at order cancellation
- Consumed permanently when loan repayment completes (handled by Ledger Service)

---

## 8. Security Controls Matrix

| Control | Implementation | Location |
|---|---|---|
| JWT RS256 verification | `decode_access_token(token, JWT_PUBLIC_KEY)` | `core/dependencies.py` |
| Session revocation (fast) | Redis `sk:auth:session:{sha256(token)}` | `core/dependencies.py` |
| Session revocation (fallback) | `UserSession` table DB query | `core/dependencies.py` |
| Admin session separation | `token_type == "admin"` in JWT payload | `core/dependencies.py` |
| Admin MFA (TOTP) | pyotp TOTP, KMS-encrypted secret, 5-attempt lockout | `services/auth.py`, `api/v1/admin_auth.py` |
| Force password change | Temp JWT scope `change_password`, 15-min TTL | `services/auth.py` |
| RBAC | `RequireRole([])` / `RequirePermission("")` dependencies | `core/dependencies.py` |
| Session invalidation on role change | `smembers` + delete all admin session keys | `api/v1/admin_auth.py` |
| CNIC encryption | AES-256-GCM (KMS mock / AWS KMS) | `core/kms.py`, `services/kyc.py` |
| bcrypt password hashing | `get_password_hash()` / `verify_password()` via passlib | `sk_shared/security.py` |
| Webhook HMAC-SHA256 | `hmac.compare_digest()` constant-time | `api/v1/webhooks.py` |
| Stripe signature verification | Custom `t=timestamp.v1=hash` parser | `api/v1/webhooks.py` |
| Internal token auth | `secrets.compare_digest()` | `api/v1/internal.py` |
| Admin IP allowlist (SEC-02) | `ADMIN_IP_ALLOWLIST` config, middleware check | `core/middleware.py` |
| Admin origin check (SEC-07) | `Origin`/`Referer` host comparison in staging/prod | `core/middleware.py` |
| Content-Type enforcement (SEC-03/04) | 415 if not `application/json` | `api/v1/internal.py`, `api/v1/webhooks.py` |
| Webhook payload size limit | 1 MB max | `api/v1/webhooks.py` |
| Webhook idempotency | `sk:webhook:processed:{key}` Redis key, 24h TTL | `api/v1/webhooks.py` |
| CORS | `app.sahulatkar.pk`, `admin.sahulatkar.pk` only | `main.py` |
| Security headers | HSTS, X-Frame-Options, X-Content-Type-Options, CSP | `core/middleware.py` |
| Rate limiting | Sliding window (Redis sorted sets) | `core/rate_limit.py` |
| Login lockout | 5 failures → 30-min lockout (users), 5 TOTP failures → 15-min (admins) | `services/auth.py` |
| OTP brute-force protection | 3-attempt limit with TTL | `services/auth.py`, `services/contract_signer.py` |
| Production config validation | Startup abort on insecure defaults | `config.py` |
| Audit trail | Every admin action → `AuditTrail` + Redis DLQ | `core/audit.py` |
| GDPR/PECA account deletion | PII anonymised on soft-delete | `api/v1/auth.py` |
| Prohibited product URLs | Keyword blocklist (tobacco, alcohol, gambling, ...) | `services/order_service.py` |
| CNIC presigned URL expiry | 900 seconds on S3 presigned URLs | `api/v1/kyc.py`, `api/v1/contracts.py` |
| OTP resend rate limit | 3 resends per hour per phone | `api/v1/auth.py` |

---

## 9. Data Storage & Caching Strategy

### PostgreSQL (primary persistence)

All models from `sk_shared.models.*`:
- `User`, `AdminUser`, `Role`, `UserSession`, `UserDevice` — identity
- `UserKycVerification`, `KycVerificationQueue`, `CustomerProfile` — KYC
- `Order`, `OrderStatusHistory` — order lifecycle
- `WakalahAgreement`, `MurabahaContract`, `ContractDigitalSignature` — contracts
- `PaymentTransaction`, `Loan`, `Installment`, `VirtualCard` — payments
- `Shipment`, `TrackingEvent` — delivery
- `AuditTrail` — compliance
- `HitlQueue` — human-in-the-loop
- `RiskAssessment`, `CreditLimitHistory` — credit
- `SystemParameter`, `RiskBlacklist` — admin configuration

All user-facing records use `deleted_at` soft-delete. `OrderStatusHistory` provides full state transition audit log.

### Redis Key Namespace Reference

| Key pattern | TTL | Purpose |
|---|---|---|
| `sk:auth:otp:{phone}:{scope}` | `OTP_TTL` (180s) | Hashed OTP for registration/login/reset |
| `sk:auth:token:{token}` | `OTP_TTL` | Registration payload for OTP verification |
| `sk:auth:token:{token}:reset` | `OTP_TTL` | Password reset token → user ID mapping |
| `sk:auth:otp_attempts:{phone}` | `OTP_ATTEMPTS_TTL` (300s) | Failed OTP counter |
| `sk:auth:otp_resend:{phone}` | 3600s | OTP resend counter |
| `sk:auth:session:{hash}` | `JWT_ACCESS_TTL` (900s) | User access token session |
| `sk:auth:admin_session:{hash}` | `ADMIN_SESSION_TTL` (8h) | Admin access token session |
| `sk:auth:admin_sessions:{admin_id}` | `ADMIN_SESSION_TTL` | Set of all active admin session hashes (for bulk invalidation) |
| `sk:auth:admin_totp_fail:{admin_id}` | 900s | TOTP failure counter |
| `sk:auth:admin_totp_setup_fail:{admin_id}` | 900s | MFA setup TOTP failure counter |
| `sk:contract:otp:{type}:{id}:{user}` | `OTP_TTL` | Contract signing OTP |
| `sk:contract:otp_attempts:{...}` | `OTP_ATTEMPTS_TTL` | Contract signing OTP failures |
| `sk:rate_limit:{scope}:{key}` | `window` | Rate limit sorted set |
| `sk:webhook:processed:{key}` | 86400s | Webhook idempotency flag |
| `sk:payment:idempotent:{scope}:{user}:{key}` | 86400s | Down-payment idempotency cache |
| `sk:audit:dlq` | persistent | Failed audit trail records |
| `sk:admin:dashboard:summary` | `ADMIN_DASHBOARD_CACHE_TTL` (60s) | Cached dashboard KPIs |

### Redis Queues (lists, LPUSH / BRPOP)

| Queue name | Pushed by | Consumed by |
|---|---|---|
| `PRODUCT_EXTRACT` | `OrderService.initiate()` | Product Service |
| `PAYMENT_INITIATE` | `payments.py` | Payment Orchestrator |
| `VCN_ISSUE` | `payments.py` | Payment Orchestrator |
| `PAYMENT_WEBHOOK` | `webhooks.py` | Payment Orchestrator |
| `NOTIFICATION_SMS` | `orders.py` (cancel) | Notification Service |

### Redis Pub/Sub Channels

| Channel | Published by | Subscribed by |
|---|---|---|
| `delivery.status_changed` | Notification/Delivery Service | Gateway `delivery_event_listener` |
| `delivery.confirmed` | Notification/Delivery Service | Gateway `delivery_event_listener` |
| `order.cancelled` | Gateway `orders.py` | Payment Orchestrator |
| `loan.created` | Gateway `contract_signer.py` | Ledger Service |
| `payment.down_payment_confirmed` | Gateway `internal.py` | Ledger Service |

---

## 10. RBAC Permission Matrix

| Role | Permissions |
|---|---|
| `super_admin` | `all_actions`, `manage_admins` |
| `risk_officer` | `manage_risk`, `read_blacklist`, `read_risk`, `read_user_financials`, `read_reports`, `read_user`, `manage_system` |
| `kyc_reviewer` | `manage_kyc_queue`, `read_user`, `read_compliance`, `read_audit` |
| `analyst` | `read_reports`, `read_risk`, `read_user_financials`, `read_financials`, `read_analytics` |
| `support` | `read_user`, `read_order`, `read_support` |
| `operations_manager` | `manage_users`, `update_user`, `manage_orders`, `read_order`, `manage_payments`, `read_reports`, `read_user`, `read_partners`, `read_support` |
| `credit_risk_analyst` | `read_risk`, `read_user_financials`, `read_reports`, `update_user` |
| `fraud_analyst` | `manage_risk`, `read_blacklist`, `manage_system`, `read_user` |
| `cs_agent` | `read_user`, `read_order`, `read_support` |
| `finance_analyst` | `read_financials`, `read_reconciliation`, `read_reports`, `manage_payments` |
| `compliance_officer` | `read_compliance`, `manage_kyc_queue`, `read_audit`, `read_user` |
| `marketing_manager` | `read_marketing`, `read_analytics`, `read_reports`, `read_partners` |

`all_actions` bypasses all per-permission checks. Permissions are embedded in the JWT at login time and re-embedded on role change (after old sessions are invalidated).

---

## 11. Bug & Gap Resolution Log

**Historical note:** an earlier generation of bugs, gaps, and missing features (tracked as `BUG-*`, `GAP-*`, `SEC-*`, `MISS-*`, `TASK-*`, `GW-BL-*` IDs — around 40 items covering things like missing password reset, missing webhooks, admin IP allowlisting, order cancellation credit-restore, etc.) was resolved well before this revision and is no longer itemized here; all of it was re-confirmed present in the current codebase during this pass. What follows is the disposition that actually matters for a team integrating a new frontend today: the Gateway-specific findings from the 2026-08 cross-service audit (`docs/PRODUCTION_GAPS_REPORT_2026-08.md`), each independently re-verified against the current source (not just trusted from that report's own claims).

### CRITICAL findings scoped to Gateway — verified FIXED

| Finding | Verified disposition |
|---|---|
| Admin login JWT collision: RS256 signing is deterministic and `exp` is second-granularity, so two admin logins for the same admin in the same second produced a byte-identical token → identical `token_hash` → `UNIQUE constraint failed: admin_sessions.token_hash` | **FIXED.** `apps/gateway/src/services/auth.py::admin_login` now includes a random `"jti": uuid.uuid4().hex` claim in every admin JWT payload, guaranteeing token/hash uniqueness even for same-second logins. |
| `orders.product_snapshot` existed in real Postgres (migration 016, hardened by 052) but was never declared on the SQLAlchemy `Order` model — ORM/migration drift that silently broke any ORM-driven schema (including the test suite) | **FIXED.** `packages/shared-python/sk_shared/models/order.py` now declares `product_snapshot: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)`. |
| Admin Orders panel (`admin_orders.py`) wrapped queries in bare `try/except Exception` and returned empty/404 on any real SQL error, hiding genuine failures from admins investigating fraud/disputes | **FIXED.** The list/detail queries no longer swallow exceptions; product-name resolution was moved out of a Postgres-only `->>` JSONB operator (which broke on the sqlite test engine and drove the original silent-catch) into a portable Python helper (`_snapshot_name`). |
| System Parameters admin panel (`admin_system.py`) was a complete facade — full CRUD/audit/caching but read back only by its own `GET`, with real values hardcoded in `contract_generator.py`/`order_service.py` | **FIXED.** `src/services/system_parameters.py::get_effective_system_parameters()` is now called from `OrderService.initiate()` (`max_active_orders`), `ContractGeneratorService` (`wakalah_validity_days`, `murabaha_validity_days`, `profit_rate_3m/4m/6m/12m`), and `admin_finance.py` (`credit_loss_provision_rate_pct`, `gst_rate_pct`). An admin changing these values now genuinely changes live contract/order behavior. |

*(The remaining 8 CRITICALs in the 2026-08 report — double-charge/idempotency and event-durability issues in Payment Orchestrator, the billing-sweep crash and Credit Engine dead-scoring-layer issues in Ledger Service/Credit Engine, and the SSRF/cardholder-data issues in Product Service — are outside Gateway's code and are not re-verified in this document; see that report for their service-specific disposition.)*

### HIGH findings scoped to Gateway — verified FIXED

| Finding | Verified disposition |
|---|---|
| `loan.created` event published to Redis before the enclosing DB transaction committed — a fast consumer (Ledger Service) could query for a loan that didn't exist yet | **FIXED.** `ContractSignerService.sign_murabaha()` no longer publishes directly; it returns a `(channel, message)` tuple to the caller. `api/v1/contracts.py::sign_murabaha` publishes it only after `db.commit()` succeeds (best-effort — a publish failure there is logged but does not fail the already-committed request). |
| No admin recovery path for an order stuck at `pending_vcn` after a failed VCN issuance — only a read-only view existed | **FIXED.** `admin_orders.py` now has `POST /{order_id}/retry-vcn`, which re-queues a fresh VCN issuance job (same shape as `POST /payments/vcn/issue` pushes) and only accepts orders currently at `pending_vcn`. |
| `validated_by_shariah_board=True` hardcoded on every Murabaha contract with no backing approval record | **FIXED.** New `ShariahBoardApproval` model (`packages/shared-python/sk_shared/models/contracts.py`) with admin CRUD at `POST/GET /admin/compliance/shariah-board-approvals`. `ContractGeneratorService` now sets `validated_by_shariah_board` to `True` only when a `ShariahBoardApproval` row exists for the exact `template_version` in use — otherwise `False`, not a hardcoded truth. |

*(HITL `sla_deadline` never escalating, the flat 10s cross-service HTTP timeout with no retry, prohibited-category re-checking, and duplicated product-extraction logic were also listed as HIGH/MEDIUM in the 2026-08 report and scoped partly to Gateway — these were not individually re-verified in this pass and should be treated as open unless separately confirmed.)*

Regression tests for the fixes above exist in `apps/gateway/tests/test_api/test_admin_auth.py` (single-session enforcement exercising the real `admin_sessions` table), `test_admin_orders.py`, `test_api/test_admin_system.py` (`test_max_active_orders_honors_admin_system_parameter` proves an admin-changed `SystemParameter` actually changes `OrderService.initiate` behavior), and `test_api/test_contracts.py` (Shariah board approval gating both directions).

---

## 12. Test Coverage

Re-verified against `apps/gateway/tests/` as of 2026-08-28 — the suite has grown substantially since the original April audit (34 test files, up from 7 originally documented). Running `cd apps/gateway && ../../.venv/Scripts/python.exe -m pytest -q` gives **238 passed, 5 failed** (223s runtime). All 5 failures are pre-existing and unrelated to the CRITICAL/HIGH fixes verified in §11 (confirmed by the 2026-08 report's `git stash` A/B comparison and re-confirmed here by inspection):

- `test_api/test_missing_coverage.py::test_installment_amounts_exclude_down_payment` — test-suite bug (`not` applied to a SQLAlchemy column filters out all rows, not a product bug)
- `test_api/test_payments_flow.py::test_down_payment_succeeds_with_correct_amount`, `::test_installment_payment_succeeds`, `::test_duplicate_down_payment_rejected` — tied to a Payment Orchestrator `_dev_simulate_fulfillment` environment-string-comparison HIGH finding, not a Gateway CRITICAL
- `test_services/test_contract_generator.py::test_generate_wakalah_fetches_customer_profile` — a KMS/`CustomerProfile.cnic` type-coercion issue unrelated to any of the 3 Gateway-scoped CRITICAL fixes

| Test file | What is validated |
|---|---|
| `test_api/test_auth.py`, `test_auth_full.py` | Registration, OTP verify/resend, login, refresh, 5-strike lockout |
| `test_api/test_admin_auth.py` | Admin login incl. MFA/TOTP, force-password-change, **single-session enforcement against the real `admin_sessions` table** (regression test for the CRITICAL jti-collision fix) |
| `test_api/test_admin_kyc_full.py`, `test_kyc.py` | KYC upload/submit/queue claim/approve/reject; RBAC enforcement |
| `test_api/test_audit_trail.py` | Audit record on admin action; DLQ write on failure |
| `test_api/test_credit_status.py` | Credit status/history correctness + pagination |
| `test_hard_gate.py` | VCN gate state checks (`CONTRACTS_PENDING`/`CONTRACTS_SIGNED`/`DOWN_PAYMENT_RECEIVED`) |
| `test_services/test_delivery_events.py` | Delivery pub/sub handlers |
| `test_api/test_admin_dashboard.py`, `test_admin_analytics.py` | Dashboard KPIs, revenue/growth/product analytics |
| `test_api/test_admin_risk.py` | Blacklist CRUD |
| `test_api/test_admin_contracts.py`, `test_contracts.py` | Contract generation/signing incl. **Shariah board approval gating both directions** (regression test for the HIGH validated_by_shariah_board fix) |
| `test_api/test_hitl.py` | HITL queue claim/resolve/escalate |
| `test_api/test_admin_payments.py` | Admin payment transaction views |
| `test_api/test_rbac_enforcement.py` | Cross-cutting permission checks |
| `test_api/test_payments_flow.py` | End-to-end down-payment/installment/VCN flow (3 pre-existing failures, see above) |
| `test_api/test_admin_users_mgmt.py` | Admin user suspend/blacklist/credit-limit |
| `test_api/test_admin_system.py` | System parameter CRUD + cache invalidation, **`test_max_active_orders_honors_admin_system_parameter`** (regression test for the CRITICAL system-parameters-facade fix) |
| `test_api/test_rate_limiting.py` | Sliding-window rate limiter |
| `test_api/test_missing_coverage.py` | Assorted edge cases (1 pre-existing failure, see above) |
| `test_api/test_orders.py`, `test_admin_orders.py` | Order lifecycle incl. prohibited-category blocking; admin order list/detail/status-override/refund/restructure/retry-vcn |
| `test_api/test_webhooks.py` | Webhook signature/idempotency/size-limit checks |
| `test_api/test_internal.py` | Internal service callbacks |
| `test_api/test_admin_compliance.py` | Audit trail search, Shariah audit log |
| `test_services/test_contract_generator.py` | Wakalah/Murabaha PDF generation (1 pre-existing failure, see above) |
| `test_services/test_kyc_service_unit.py`, `test_kyc_service_additional.py` | KYC service unit coverage |
| `test_services/test_order_recovery_sweep.py`, `test_hitl_sla_sweep.py` | Background sweep jobs |
| `test_services/test_http_client_correlation.py` | `InternalServiceClient` correlation-ID propagation |

**Not yet covered by dedicated test files:** the Phase-4 admin modules added since the April audit — `admin_approvals.py`, `admin_developer.py`, `admin_documents.py`, `admin_finance.py`, `admin_logs.py`, `admin_marketing.py`, `admin_notifications.py`, `admin_reports.py` — and the newer customer-facing `cart.py`, `support.py`, `notifications.py` have no dedicated test files under `apps/gateway/tests/` as of this pass. Treat their behavior as unverified until tests are added; read the source directly (all listed in §5.3/§5.4) rather than assuming test coverage exists.

**Test infrastructure:** In-memory SQLite (`:memory:?cache=shared`), FakeRedis, per-test DB setup, `test_user` creates an `active`-status user with a valid access token, `test_admin` creates a `super_admin` with `all_actions`.

---

## 13. Deployment Checklist

### Required Environment Variables (production)

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL async URL (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Redis connection URL |
| `JWT_PRIVATE_KEY` | RS256 private key PEM (for token signing) |
| `JWT_PUBLIC_KEY` | RS256 public key PEM (for token verification) |
| `KMS_KEY_ARN` | AWS KMS key ARN (replaces mock AES key) |
| `INTERNAL_SERVICE_TOKEN` | Shared secret for inter-service calls |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook endpoint secret |
| `JAZZCASH_WEBHOOK_SECRET` | JazzCash HMAC secret |
| `SAFEPAY_WEBHOOK_SECRET` | SafePay HMAC secret |
| `S3_BUCKET` | S3 bucket for contract PDFs and KYC documents |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | AWS credentials |
| `SECP_LICENSE_NUMBER` | SECP regulatory license number (printed on contracts) |
| `ADMIN_IP_ALLOWLIST` | Comma-separated IPs allowed to access admin login |
| `ENVIRONMENT` | Set to `production` to enable all security checks |

### Pre-flight Validation

The service **aborts startup** if `ENVIRONMENT=production` and any of the following are at defaults:
- `KMS_MOCK_KEY_HEX` at the insecure default value
- `INTERNAL_SERVICE_TOKEN` = `"local-internal-token"`
- Missing `STRIPE_WEBHOOK_SECRET`, `S3_BUCKET`, `SECP_LICENSE_NUMBER`, `JWT_PRIVATE_KEY`

### Operational Requirements

- **PostgreSQL migrations** must include `system_parameters` and `risk_blacklist` tables (validated at startup with a warning if absent)
- **Redis AOF persistence** recommended — session data and rate-limit state must survive Redis restarts
- **`tmp/contracts/`** must be added to `.gitignore` — dev-generated PDFs should not be committed
- **Monitoring alerts** should be configured for:
  - `AUDIT_DLQ_WRITE_FAILED` in logs (compliance data loss)
  - `Delivery listener died` in logs (watchdog restart)
  - Admin login failure spikes
  - Rate limit hit rate above threshold
- **NADRA / Shufti** mock clients must be replaced with real API clients before go-live
- **Prometheus** metrics endpoint is at `/metrics` — wire to Grafana or equivalent

---

*This document was originally written 2026-04-27 and corrected/re-verified 2026-08-28 against the current `apps/gateway` source, including the file registry, API catalog, and the Gateway-specific CRITICAL/HIGH findings from `docs/PRODUCTION_GAPS_REPORT_2026-08.md` (§11). Sections 2-4, 6-10, and 13 were spot-checked but not exhaustively re-derived; treat the §5 file registry, §6 endpoint catalog, §11 disposition, and §12 test results as the most current parts of this document.*
