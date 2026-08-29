# Frontend Integration Guide

**Last verified:** 2026-08-28

## Read this first

The previous customer and admin Next.js frontends (`apps/web-customer/`, `apps/web-admin/`) are being **discarded and rebuilt from scratch**. This document is not a description of those old apps — it's a from-scratch integration brief for whoever builds the new ones (human or AI agent), based on what the backend actually does today, verified against the real running code and a real end-to-end test, not against old scaffolding.

The backend is stable and independently verified: all 6 microservices, an automated cross-service E2E test covering the full customer purchase journey (`tests/e2e/test_order_lifecycle.py`, passing against a real `docker compose up` — zero mocking), and per-service integration references in this same folder (`gateway_microservice_audit.md`, `product_service_audit.md`, `credit_engine_audit.md`, `payment_orchestrator_audit.md`, `ledger_service_audit.md`, `notification_service_audit.md`, `infrastructure_packages_audit.md`). **Read the Gateway doc alongside this one** — almost everything a customer or admin frontend calls goes through Gateway, and that doc has the full endpoint catalog, request/response field names, Redis key namespace, and RBAC matrix. This doc is the cross-cutting "how the pieces fit into screens" layer on top of that.

---

## 1. One rule that matters more than any other

**Every frontend talks to Gateway (`apps/gateway/`) only.** No other microservice exposes a public HTTP surface intended for a browser or mobile app. Product Service, Credit Engine, Payment Orchestrator, Ledger Service, and Notification Service are called by Gateway (or by each other) server-side; Gateway is the single BFF. If you find yourself wanting to call `payment-orchestrator:8000/...` or `ledger-service:8000/...` directly from a frontend, stop — that's a sign the flow needs a new Gateway endpoint instead, not a direct call. (Ledger Service in particular authenticates via unsigned trust-based headers with no JWT verification — see `ledger_service_audit.md` section 2 — calling it directly from a browser would be a real security hole, not just an architecture violation.)

Base path for everything: `/api/v1/*` on the Gateway service. Local dev default: `http://localhost:8000` (check `infra/docker/docker-compose.yml` for the exact port mapping in the current compose file).

---

## 2. Auth model

- **Customers**: phone-number + OTP registration, optional password login afterward. JWT (RS256) access token (15 min TTL) + refresh token. Send `Authorization: Bearer <access_token>` on every authenticated call.
- **Admins**: separate login (`POST /api/v1/admin/auth/login`), IP-allowlist-gated, requires TOTP MFA after first setup, separate JWT `token_type: "admin"` with permissions embedded in the token payload. Same `Authorization: Bearer` header, but tokens are not interchangeable between customer and admin surfaces.
- Session revocation is fast (Redis-backed) with a DB fallback — logging out or an admin role change invalidates tokens near-instantly, so don't cache "is this token still valid" client-side beyond the access-token TTL.
- CORS in the current backend config is locked to `app.sahulatkar.pk` and `admin.sahulatkar.pk`. **You will need to update the allowed origins in `apps/gateway/src/main.py` for local dev (e.g. `localhost:3000`) and for whatever domains the new frontends actually deploy to** — this is expected setup work, not a bug.

### Local-dev-only conveniences (never rely on these outside local/test environments)

- Registration OTP is hardcoded to `"123456"` when `ENVIRONMENT=local` (`apps/gateway/src/services/auth.py`). In non-production environments the real OTP is also echoed back as `dev_otp` in the response body, so you never have to read Redis or logs to get it.
- Contract-signing OTPs (Wakalah/Murabaha) are similarly echoed as `dev_otp` in the `POST /contracts/{wakalah,murabaha}/generate` response bodies outside production.
- **NADRA CNIC verification mock**: any well-formed CNIC (`XXXXX-XXXXXXX-X`) auto-verifies *except* one ending in `-9`, which simulates a registry mismatch/rejection — use this to test the KYC-rejected path deliberately.
- **Shufti OCR/liveness mock**: always returns CNIC `12345-1234567-1` and succeeds, unless the submitted document/video URL contains the literal substring `"invalid"` (OCR failure) or `"spoof"` (liveness failure) — use these substrings in test fixture URLs to exercise KYC failure UI.

None of this exists once `ENVIRONMENT=production` — build your UI against the real flows (OTP entry, document upload, rejection handling), just use these shortcuts to drive the flows quickly in dev.

---

## 3. The customer journey, screen by screen

This is the golden path the E2E test (`tests/e2e/test_order_lifecycle.py`) actually exercises end-to-end — treat it as the executable source of truth for exact request/response shapes when the prose below isn't enough.

| Step | Screen | Backend calls | Notes |
|---|---|---|---|
| 1 | Register | `POST /auth/register/initiate` → `POST /auth/verify-otp` | Returns access+refresh tokens on success. |
| 2 | KYC | `POST /kyc/start` → `POST /kyc/upload/{cnic_front\|cnic_back\|liveness_video}` → `PUT /kyc/profile` → `POST /kyc/submit` → poll `GET /kyc/status` | Submission runs OCR + liveness + NADRA check synchronously, then queues for manual admin review if all pass. Status moves to `active` only after admin approval — **build a "pending review" UI state**, don't assume instant approval. |
| 3 | Paste a product URL | `POST /orders/initiate` | Runs KYC-active check, credit check, and a prohibited-category check (tobacco/alcohol/gambling keyword blocklist) before accepting. Non-2xx here needs distinct UI per failure reason (KYC not done vs. no credit vs. prohibited item) — check the error `detail` code. |
| 4 | Wait for offer | Poll `GET /orders/{id}/offer` | Extraction (URL scraping) runs async in Product Service; this endpoint returns a pending/failed/ready status. **10-minute extraction timeout** — design the polling UI to give up and show a retry/failure state well before that, with reasonable poll intervals (a few seconds), not a tight loop. |
| 5 | Accept offer | `POST /orders/{id}/accept` | Body includes chosen installment plan (3/6/12 months — see `product_service_audit.md` for the Murabaha pricing shape). |
| 6 | Sign Wakalah | `POST /contracts/wakalah/generate` → `POST /contracts/wakalah/sign` | Generate returns a PDF + issues an OTP; sign requires that OTP. |
| 7 | Sign Murabaha | `POST /contracts/murabaha/generate` → `POST /contracts/murabaha/sign` | Requires Wakalah already signed. Signing **auto-creates the Loan + full installment schedule** server-side — nothing for the frontend to construct. |
| 8 | Down payment | `POST /payments/down-payment` | Supports an idempotency key — **always send one** (e.g. a client-generated UUID per attempt) so a double-tap or retry-on-timeout can't double-charge. |
| 9 | Wait for VCN issuance | Poll `GET /payments/vcn/status/{order_id}` | VCN issuance is hard-gated on `contracts_signed` + `down_payment_received` — if you see a `VCN_GATE_NOT_PASSED` or `DOWN_PAYMENT_NOT_CONFIRMED` error code, it means the state machine isn't where you think it is; don't just retry blindly, re-fetch order status. |
| 10 | Checkout runs automatically | (no frontend call) | This is the interesting part of SahulatKar: a backend Playwright agent executes the actual purchase on the merchant's site using the issued virtual card. The frontend has nothing to do here except show progress/waiting UI. |
| 11 | Track order | `GET /orders/{id}` / `GET /orders/{id}/tracking` | Shows shipment status once registered with the courier. |
| 12 | Manage installments | `GET /payments/schedule/{order_id}`, `POST /payments/installment/{id}/pay` | Amount tolerance is ±1 PKR — don't round client-side in a way that could produce a mismatch. |

**Full order state values** (`Order.status`): `url_received → offer_presented → offer_accepted → contracts_pending → contracts_signed → down_payment_received → pending_vcn → purchase_confirmed → delivery_pending → delivered`, with `extraction_failed` and `cancelled` as terminal off-ramps reachable from most pre-payment states via `POST /orders/{id}/cancel`. Drive your UI's progress indicator off this exact state list — see `gateway_microservice_audit.md` section 7 for the full diagram and the credit-reservation semantics tied to it.

---

## 4. The admin journey, module by module

Admin roles are real and enforced server-side (12 roles, full permission matrix in `gateway_microservice_audit.md` section 10) — **build role-aware navigation**, don't just hide menu items client-side as the only gate; the backend will 403 regardless, but showing a screen a role can't use is a bad UX default. Modules, and the endpoints backing each:

- **Dashboard** — `GET /admin/dashboard/summary` (Redis-cached KPIs), `GET /admin/analytics/*`.
- **KYC review queue** — `GET /admin/kyc/queue`, claim/approve/reject. This is where every customer's KYC submission actually gets unblocked — don't treat it as optional/secondary in the admin IA, it's on the customer's critical path.
- **HITL (human-in-the-loop) queue** — `GET /admin/hitl/queue`, claim/resolve/escalate. Populated when an automated checkout fails and needs a human to look at it. `sla_deadline` is stored per entry but — as of this writing — nothing escalates or alerts on it automatically; if your admin UI wants proactive alerting on SLA breach, that logic needs to live in the frontend/notification layer for now, the backend won't push it to you.
- **Orders** — `GET /admin/orders`, force-status-transition endpoint exists but is a manual override, not a normal flow.
- **Payments / Installments** — transaction list, refund initiation, fee waivers, force-mark-paid.
- **Users** — search, status changes, blacklist, manual credit-limit override.
- **Risk** — blacklist management.
- **System Parameters** (`GET/POST /admin/system/parameters`) — **known gap, real as of this writing**: verify current status in `gateway_microservice_audit.md`'s findings section before building UI here. It was previously a complete facade — full CRUD with audit logging, but the values it stores were never actually read by the pricing/contract logic that should use them (down-payment %, profit rates, risk thresholds are hardcoded elsewhere in the code). If still true, don't build an admin UI that implies "change this number and contracts update" without the founder confirming the backend wiring is done.
- **Compliance** — audit trail search, Shariah compliance audit log.
- **Finance** — Gateway has its own `admin_finance.py`; there is a *separate*, richer finance/reporting surface directly on Ledger Service (`GET /entries`, `GET /accounts`, `GET /accounts/{code}/ledger`, P&L/trial-balance/balance-sheet/shariah-audit reports) that is **not currently proxied through Gateway** — see `ledger_service_audit.md` sections 2-3 before building any finance dashboard. You'll likely need to either add a Gateway proxy layer for it or get an explicit decision from the founder on how it should be exposed to an admin frontend safely.
- **Partners / Support** — read-mostly list views today.

---

## 5. Real-time updates

There is **no WebSocket or SSE endpoint** in the current backend for pushing state changes to a frontend. Every "live" status a screen needs (offer ready, KYC approved, VCN issued, delivery updates) is obtained by **polling** the relevant `GET` endpoint. Build your data layer around polling with sane backoff (a few seconds, capped, with a visible timeout/retry state), not an assumption of push updates — this is a real architectural fact of the current backend, not a to-do item, unless the founder wants to add SSE/WebSocket support as new backend work.

---

## 6. Design system

No constraints exist from the discarded frontends worth carrying forward — the old apps used TailwindCSS + Shadcn/UI with an Emerald-700/Indigo-900 palette, but since they're being thrown away, treat brand/design decisions as open unless the founder specifies otherwise.

---

## 7. Running the backend locally

See `infrastructure_packages_audit.md` for the verified, current `docker compose` invocation and service/port list, and `tests/e2e/README.md` for a fully worked example (with real request/response payloads) of driving the entire customer journey against a live local stack — that test is the most reliable "does my understanding of the API match reality" check available, since it's the only thing in this repo that's actually run start-to-finish against real Postgres/Redis/Docker networking rather than mocks.
