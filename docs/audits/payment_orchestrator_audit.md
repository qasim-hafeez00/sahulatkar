# Payment Orchestrator — Integration Reference

Rewritten 2026-08-28 as a direct-from-code reference, not a scored audit. Every claim below is
grounded in the current source under `apps/payment-orchestrator/` (plus the parts of
`apps/gateway/` and `infra/k8s/` needed to establish who actually calls this service). This
replaces an earlier version of this file that only documented `payments.py`/`webhooks.py` and
carried an invented "Production Readiness: ~90%" score — the real `src/api/v1/` also has
`admin.py`, `mandates.py`, and `vcn.py`, and the real integration path for money movement is not
what the old doc described at all (see section 5 — it matters more here than in any other service
in this fleet, because it decides who is allowed to touch PAN/CVV).

Full test suite as of this writing (`../../.venv/Scripts/python.exe -m pytest -q` from
`apps/payment-orchestrator/`): **242 passed, 0 failed** (~107s).

---

## 1. Service Purpose

Payment Orchestrator owns three things for SahulatKar's BNPL platform: (1) driving down-payment,
installment, and refund charges through four Pakistani payment rails (JazzCash, SafePay, Raast
IBFT, EasyPaisa) plus Stripe/Lithic for card issuing, (2) the full lifecycle of single-use Virtual
Card Numbers (VCNs) used to actually buy the product at the merchant, and (3) settlement
reconciliation against gateway settlement files. It does **not** own `Order`, `Loan`, or
`Installment` state — those belong to Gateway and Ledger Service — so every mutation here is
either a direct field on this service's own tables (`PaymentWorkflow`, `RefundWorkflow`,
`VirtualCard`, `PaymentMandate`, `OutboxEvent`) or an emitted event that Gateway/Ledger react to
asynchronously. It sits entirely inside the private network — no browser or mobile app is meant to
reach it directly (section 5).

## 2. API Endpoint Catalog

Base path: `/api/v1`. Five routers are mounted (`src/api/routes.py`): `payments.py` (prefix
`/payments`), `vcn.py` (prefix `/payments`, i.e. `/payments/vcn/*`), `mandates.py` (prefix
`/payments/mandates`), `admin.py` (prefix `/admin/payments`), `webhooks.py` (no prefix, i.e.
`/webhooks/*`). Every route in `payments.py`/`vcn.py`/`mandates.py` that isn't explicitly marked
internal requires a customer bearer JWT with a `user_id` claim (`get_current_user`,
`src/core/dependencies.py`), verified RS256 against `settings.JWT_PUBLIC_KEY` — the same public
key Gateway signs with. Admin routes require an admin JWT with an `admin_id` claim
(`get_current_admin`) **and** an explicit role check via `RequireRole([...])` (unlike credit-engine,
this service does enforce per-route role gating). Internal-only routes require header
`X-Internal-Token` matched constant-time against `settings.INTERNAL_API_TOKEN`
(`require_internal_token`).

**Read section 5 before building anything against these** — despite being fully built,
JWT-gated, and (per network policy) reachable from Gateway's pods, nothing in Gateway's own source
actually calls most of this API over HTTP today. Real customer traffic reaches this service's
business logic through two Redis queues instead, not through these routes directly.

### `payments.py` — built as customer-facing (Customer JWT), but see section 5

**`POST /payments/down-payment`** (rate-limited 10/60s per IP) — body `DownPaymentRequest
{order_id: int, method: "safepay"|"jazzcash"|"raast", amount_pkr: Decimal(2dp) >0,
idempotency_key: str (8-128 chars)}`. Validates `Order.status == CONTRACTS_SIGNED`, validates
`amount_pkr` is within `DOWN_PAYMENT_MIN_PCT`-`DOWN_PAYMENT_MAX_PCT` (25%-40%) of `order.total_amount`,
picks a gateway via `GatewayRoutingEngine` (health-based failover), creates a durable
`PaymentWorkflow` row, and either redirects (SafePay/Raast — async, webhook confirms later) or
charges synchronously (JazzCash) and immediately queues VCN issuance. Response
(`DownPaymentResponse`): `status: "pending"|"success"`, `order_id`, `payment_workflow_id`,
`payment_session_url` (SafePay redirect URL, when async), `gateway_txn_id`, `idempotency_key`.
Double-submit-safe via a Redis pre-check plus the idempotency key on `PaymentWorkflow`.

**`POST /payments/pay-installment`** — body `PayInstallmentRequest {installment_id, method,
payment_method_id?}`. Charges the installment's `total_amount` immediately (sync-only path — no
async-redirect branch here, unlike down-payment) and emits `payment.installment_paid` via the
outbox; does **not** set `Installment.status` itself (Ledger Service owns that transition).
Guarded by a per-installment Redis lock (`sk:po:lock:installment:{id}`, 30s TTL,
`_INSTALLMENT_LOCK_TTL_SECONDS`) plus a `SELECT ... FOR UPDATE` re-check — see section 4, this is
the fixed double-charge guard. Response (`PayInstallmentResponse`): `success: bool`, `txn_id: int`,
`paid_at: str (ISO)`, `next_installment_id: int | None`.

**`POST /payments/refund`** — body `RefundRequest {order_id, amount_pkr: Decimal(2dp) >0,
reason (3-255 chars), refund_reference (8-128 chars, idempotency key)}`. Finds the order's
earliest successful `PaymentTransaction`, computes `refundable_amount = original_amount -
sum(non-failed refunds already on this order)`, rejects if the request exceeds that. Calls
`RefundOrchestrator.initiate_refund`, which calls the gateway adapter's `refund()` — SafePay/some
paths settle synchronously (`RefundStatus.SETTLED` immediately), others go `PENDING` until a
`/webhooks/{gateway}/refund` callback settles them (section 3). Response (`RefundResponse`):
`refund_id`, `order_id`, `amount_pkr`, `status: "initiated"|"pending"|"success"|"failed"`,
`gateway_refund_id`, `reason`.

**`POST /payments/down-payment/{payment_workflow_id}/retry`** — no body. Only valid when the
workflow is `FAILED` or `EXPIRED`; mints a fresh idempotency key (`{original}_retry_{uuid8}`) so it
doesn't collide with the stale workflow, re-selects a gateway, and re-attempts. Response: `status:
"retried"`, `new_workflow_id`, `gateway`, `gateway_txn_id`, `idempotency_key`.

**`GET /payments/history/{order_id}`** — full `PaymentTransaction` + `PaymentWorkflow` history for
an order the caller owns. Response: `{order_id, transactions: [{id, amount, currency, gateway,
gateway_txn_id, status, created_at}], workflows: [{id, status, gateway, amount_pkr, created_at}]}`.

**`POST /payments/internal/trigger-installment`** (`X-Internal-Token`, `include_in_schema=False`)
— legacy billing-trigger path; picks Raast automatically if the user has a valid mandate, retries
up to `MAX_INSTALLMENT_RETRIES` (3) with delays `[0, 24, 48]` hours, emits
`payment.installment_failed` (plain `redis.publish`, not outbox — see section 4) after exhausting
retries.

**`POST /payments/internal/installments/{installment_id}/auto-collect`** (`X-Internal-Token`,
`include_in_schema=False`) — this is the endpoint Ledger Service's billing sweep actually drives
today, via `payment-orchestrator`'s own event listener self-calling over HTTP (see section 3/5).
Same Raast-mandate-first logic, same idempotency guard pattern as `pay_installment`
(`_installment_already_settled` equivalent inline, `SELECT ... FOR UPDATE`, no Redis lock on this
specific route — the caller is a single internal trigger, not a customer double-tap risk).

### `vcn.py` — mixed: customer JWT + one internal-only route

**`POST /payments/vcn/issue`** (rate-limited 5/60s per IP, Customer JWT) — body `VcnIssueRequest
{order_id, amount_pkr: Decimal(2dp) >0, merchant_domain?}`. Requires a signed `MurabahaContract`
and `Order.status` in `{CONTRACTS_SIGNED, DOWN_PAYMENT_RECEIVED}`; rejects if `amount_pkr` drifts
>5% from `order.total_amount` (`PRICE_DRIFT_EXCEEDED`). Idempotent — returns the existing card if
one is already issued for the order. Issues via Stripe Issuing (or Lithic if
`FEATURE_LITHIC_ENABLED`, off by default pending KYB approval). Response (`VcnIssueResponse`):
`vcn_id`, `order_id`, `status`, `pan` (masked, `**** **** **** XXXX`), `expiry_month`,
`expiry_year`, `cvv` (always literal `"***"` — never real), `issued_at`, `expires_at`. **Real
PAN/CVV never appear in this response.**

**`POST /payments/vcn/{vcn_id}/void`** (rate-limited 10/60s, Customer JWT, order-ownership checked)
— query/body param `reason` (default `"manual_void"`). Cancels the card on Stripe with 3 retries
(1s between); if Stripe cancellation still fails after 3 attempts, **voids the local row anyway**
and logs an error rather than blocking (see section 4 — a frontend must not assume "voided" here
means the card is actually dead at the card network). Response: `{status: "voided", vcn_id, reason,
stripe_canceled: bool}`.

**`GET /payments/vcn/{order_id}/status`** (Customer JWT) — response (`VcnStatusResponse`): `status`,
`charged_amount: float`, `is_used: bool`, `issued_at`, `expires_at`.

**`GET /payments/internal/vcn/{order_id}/decrypt`** (`X-Internal-Token`, rate-limited 30/60s) —
**internal-only, real plaintext PAN/CVV.** Only the Product Service checkout agent calls this.
Response (`VcnDecryptResponse`): `vcn_id`, `order_id`, `pan` (full 16 digits), `expiry_month`,
`expiry_year`, `cvv` (real 3-digit), `cardholder_name`, `expires_at`. **This route must never be
exposed to any frontend, admin dashboard, or logged in full — a new integration engineer should
treat this as the single most sensitive endpoint in the entire platform.**

### `mandates.py` — customer-facing, Raast/JazzCash auto-debit setup

**`POST /payments/mandates`** (also aliased at `POST /payments/mandates/setup`, legacy,
`include_in_schema=False`) — body `MandateSetupRequest {gateway: "raast"|"jazzcash",
payer_identifier: str (IBAN or phone), max_amount_per_txn?: Decimal}`. Calls the gateway's
`setup_mandate` (400 if the gateway adapter doesn't support mandates). Response
(`MandateSetupResponse`): `mandate_id`, `status: "initiated"`, `mandate_reference`,
`payer_identifier`, `authorization_url?` (bank-app deep link), `message`. The mandate only becomes
`status="active"` after the customer authorizes it in their banking app and
`POST /webhooks/raast/mandate` fires (section 3).

**`GET /payments/mandates/`** (trailing slash) — list caller's own mandates. Response: list of
`MandateStatusResponse {mandate_reference, gateway, status, payer_identifier,
max_amount_per_txn, expires_at, last_used_at}`.

**`DELETE /payments/mandates/{mandate_id}`** (also `POST /payments/mandates/{mandate_reference}/revoke`,
legacy) — sets `status="revoked"`, `revoked_at=now`. Response: `{status: "revoked", mandate_id}`.

### `admin.py` — Admin JWT + role, used by Web Admin (being discarded, but the API stays)

Two role tiers via `RequireRole`: `_FINANCE_ROLES = ["superadmin", "finance"]` (write actions),
`_READ_ROLES = ["superadmin", "finance", "support"]` (read-only).

- **`GET /admin/payments/transactions`** (`_READ_ROLES`) — paginated `PaymentTransaction` list,
  filterable by `gateway`/`status`. `order_id` in the response is resolved via a `Loan` outer-join
  fallback (see section 4 — `PaymentTransaction.order_id` itself is always `NULL` from every
  write path in this service). Response (`PaginatedTransactions`): `items:
  [TransactionSummary{id, order_id, user_id, amount, currency, gateway, gateway_txn_id, status,
  created_at, reconciled_at}], total, page, page_size`.
- **`GET /admin/payments/vcns`** (`_READ_ROLES`) — filterable by `status`. Response: list of
  `VcnAdminSummary {vcn_id, order_id, user_id, status, masked_number, authorized_amount,
  charged_amount, issued_at, expires_at, void_reason}` — masked number only, never PAN/CVV.
- **`GET /admin/payments/gateway-health`** (`_READ_ROLES`) — live `GatewayRoutingEngine` health
  summary per gateway. Response: list of `{gateway, failure_count_window, is_degraded,
  window_seconds}`.
- **`POST /admin/payments/reconciliation`** (`_FINANCE_ROLES`) — body
  `ReconciliationImportRequest` (gateway settlement file upload/import); runs
  `ReconciliationService.reconcile`, returns `ReconciliationReport` (matched/discrepancy counts).
- **`GET /admin/payments/workflows`** (`_READ_ROLES`) — paginated raw `PaymentWorkflow` rows.
- **`POST /admin/payments/workflows/{workflow_id}/force-retry`** (`_FINANCE_ROLES`) — only valid
  from `FAILED`/`EXPIRED`; resets to `INITIATED`, increments `attempt_count`, suffixes the
  idempotency key so a fresh customer attempt doesn't collide with the reset workflow.
- **`POST /admin/payments/adjustments`** (`_FINANCE_ROLES`) — body `{order_id, amount_pkr, reason}`.
  Does **not** write a `PaymentTransaction` directly — emits `payment.adjustment_requested` via
  outbox only. **A frontend must not treat this as "money moved" — it's a request queued for
  whatever downstream consumes `payment.adjustment_requested`; confirm that consumer exists before
  promising admins an instant balance correction (not verified as part of this read — grep it
  before building UI that assumes synchronous effect).**
- **`GET /admin/payments/audit-trail/{order_id}`** (`_READ_ROLES`) — consolidated transactions +
  VCNs for an order, for dispute/support review.
- **`POST /admin/payments/reconciliation/trigger`** (`_FINANCE_ROLES`) — query params `gateway`,
  `settlement_date` (YYYY-MM-DD); fires `run_reconciliation` as a detached `asyncio.create_task`
  (fire-and-forget — the HTTP response returns immediately with `{status: "triggered"}` before the
  job finishes; there is no route to poll its completion other than re-reading the transactions it
  touched).
- **`GET /admin/payments/mandates/{user_id}`** (`_READ_ROLES`) — all mandates for a given user,
  full detail (not masked — `payer_identifier` is IBAN/phone, visible to finance/support roles).

### `webhooks.py` — gateway-only, no JWT, HMAC-verified per gateway

No JWT on any route here — auth is the vendor's own HMAC signature, verified before anything else
runs. See section 5 for the exact signature scheme per gateway and section 4 for whether these
routes are actually reachable from the public internet today (they are not, per network policy —
Gateway relays webhooks to this service via a Redis queue instead; see `payment_webhook_consumer.py`).

- **`POST /webhooks/safepay`**, **`/webhooks/jazzcash`**, **`/webhooks/raast`** — payment
  confirmation. On success status, confirms the down payment and queues VCN issuance at the
  order's **full total amount** (not the down-payment amount — see section 4, this was a real bug,
  now fixed in all three handlers). Response (`WebhookAck`): `status: "ok"|"duplicate"|"ignored"`.
- **`POST /webhooks/raast/mandate`** — mandate authorization confirmation; flips
  `PaymentMandate.status` to `"active"` or `"failed"`.
- **`POST /webhooks/{safepay,jazzcash,raast}/refund`** — async refund-completion callback; calls
  `RefundOrchestrator.settle_refund`.
- **`POST /webhooks/stripe`** — Stripe Issuing events (`issuing_transaction.created`,
  `issuing_authorization.request` — approves/declines in real time against the card's authorized
  limit, `issuing_card.updated`). Dedup keyed on Stripe's own `evt_...` event id.

### Unauthenticated

**`GET /health`** → unconditional `{"status": "ok", "service": "payment-orchestrator"}` (liveness
only — always 200 even if DB/Redis are down). **`GET /health/ready`** → checks DB/Redis/Stripe
connectivity, 503 if any is unreachable — this is the one to point a real readiness probe at, not
`/health`. **`GET /metrics`** → Prometheus scrape, no schema exposure (`include_in_schema=False`).

## 3. VCN / Payment Lifecycle State Machine

**The production-reachable flow does not go through this service's own `/payments/*` HTTP routes
at all — read section 5 first.** In production, a frontend calls **Gateway's**
`POST /api/v1/payments/down-payment`, which writes a `PaymentTransaction {status: "initiated"}` row
and pushes a `payment.initiate_requested` job onto the Redis list `sk:queue:payment_initiate`.
Payment Orchestrator's `PaymentInitiateConsumer` worker (`src/workers/payment_initiate_consumer.py`,
started in-process by `src/main.py`'s lifespan, not a separate route) pops that job, calls the
selected gateway adapter directly, and updates the **same** `PaymentTransaction` row Gateway
created (matched by `payment_id`) — it does not create a second one. The sequence a frontend
should poll/react to:

1. **`initiated`** — customer submits down payment via Gateway; `PaymentTransaction.status =
   "initiated"`. Nothing charged yet.
2. **`pending`** (async gateways: SafePay, Raast) — `PaymentInitiateConsumer` called the gateway,
   got a redirect/IBFT-pending response, set `status = "pending"`. Frontend should show a "waiting
   for confirmation" state; JazzCash (sync) skips this and goes straight to step 3.
3. **`success`** (down payment confirmed) — triggered either by `PaymentInitiateConsumer`
   confirming synchronously (JazzCash) or by the async gateway's webhook. Gateway's own
   `POST /api/v1/webhooks/payment/{gateway}` verifies the vendor HMAC and enqueues onto
   `sk:queue:payment_webhook`; Payment Orchestrator's `PaymentWebhookConsumer` picks it up, calls
   `VcnService.confirm_down_payment` (emits `payment.down_payment_confirmed` via outbox — **does
   not** mutate `Loan`/`Order` itself, BV-01 boundary rule) and then
   `VcnService.queue_issue(amount_pkr=order.total_amount)` — always the order's **full total**,
   never the down-payment amount just confirmed (see section 4, this was a live bug in all three
   `webhooks.py` handlers and the sync path, now fixed everywhere it occurs).
   `confirm_down_payment` also queues a `gateway.payment_confirmed` outbox event, which
   `OutboxPublisher` turns into an authenticated HTTP call to Gateway's own
   `POST /api/v1/internal/payments/{payment_id}/confirm` — **this is the only thing that actually
   advances `Order.status` past `CONTRACTS_SIGNED` to `DOWN_PAYMENT_RECEIVED`** in a real
   (non-dev-auto-confirm) deployment.
4. **VCN issuance queued → issued** — the `vcn.issue` outbox event is picked up by
   `OutboxPublisher` and pushed onto `sk:queue:vcn_issue`; `VcnIssueWorker` (also started
   in-process) calls `VcnService.issue_vcn`, which requires a signed `MurabahaContract` and
   `Order.status ∈ {CONTRACTS_SIGNED, DOWN_PAYMENT_RECEIVED}`, checks the 5% price-drift guard
   against `order.total_amount`, and issues via Stripe Issuing. `VirtualCard.status = "active"`,
   `authorized_amount` = product price × (1 + `VCN_BUFFER_PCT` + `FX_BUFFER_PCT`) ≈ 7% above price
   by default. A frontend can poll `GET /payments/vcn/{order_id}/status` (via Gateway — see
   `GET /api/v1/payments/vcn/status/{order_id}` in Gateway's own `payments.py`) for `status`,
   `charged_amount`, `is_used`.
5. **Checkout charge** — Product Service's checkout agent calls the internal-only
   `GET /internal/vcn/{order_id}/decrypt` (X-Internal-Token) to load the real PAN/CVV into the
   automated checkout flow. Stripe fires `issuing_authorization.request` (this service
   approves/declines in real time against `authorized_amount`) and then
   `issuing_transaction.created` on a successful charge — the latter sets `VirtualCard.is_used =
   True`, emits `vcn.charged`, and writes the Redis key `sk:vcn:charge:confirmed:{vcn_id}` that
   Product Service's `VcnVerifier.verify_charge()` polls to know the purchase actually went
   through (this write was missing until a recent fix — see section 4).
6. **Refund** (if triggered) — `RefundWorkflow.status` cycles `INITIATED → SETTLED` (synchronous
   gateway confirmation) or `INITIATED → PENDING → SETTLED` (async, confirmed later by
   `/webhooks/{gateway}/refund`), or `→ FAILED`. **Settlement here means the gateway confirmed the
   refund — it does not by itself mean the customer's ledger balance is corrected; that still
   depends on Ledger Service consuming the emitted `payment.refund_settled` event.** Do not build a
   refund button that promises an instant balance reversal on the strength of this service's
   response alone.

Installment payments follow a simpler synchronous-only version of steps 1-3 (no PENDING state
modeled in the direct `/pay-installment` path; the queue-driven `payment.installment_requested`
path used by Gateway's real installment-pay endpoint does support the async branch, mirroring
down-payment).

## 4. Known Gaps & Caveats Relevant to Integration

Verified against the current code on this pass (2026-08-28), cross-checked against
`docs/PRODUCTION_GAPS_REPORT_2026-08.md`'s Payment Orchestrator findings — not carried forward
from that report's summary table without independent verification:

- **Installment double-charge race — FIXED.** The gaps report's CRITICAL #1
  (`pay_installment`/`auto_collect_installment`, no lock) is resolved: `pay_installment`
  (`src/api/v1/payments.py:330-355`) now takes a Redis `SET NX` lock
  (`sk:po:lock:installment:{id}`, 30s TTL) before touching the DB, plus a `SELECT ... FOR UPDATE`
  re-check of `_installment_already_settled` (checks both `Installment.status == "paid"` **and**
  any existing successful `PaymentTransaction` for that installment, since Ledger Service sets the
  former asynchronously and can lag). `auto_collect_installment` has the equivalent guard. Confirm
  before relying on this for a new gateway/integration path — the lock key is
  `installment_id`-scoped, not tied to any client-supplied idempotency key, since the three
  call sites (`pay_installment`, `auto_collect_installment`, `internal_trigger_installment`) don't
  share one.
- **Outbox event durability — FIXED.** CRITICAL #2 (plain `redis.publish()`, zero durability) is
  resolved for the transactional-outbox path: `OutboxPublisher` (`src/workers/outbox_publisher.py`)
  now `XADD`s standard events to a Redis Stream (`sk:stream:outbox_events`) and delivers them via a
  consumer-group loop (`XREADGROUP` → publish to the legacy pub/sub channel → `XACK`), with
  `XAUTOCLAIM` reclaiming anything left unacknowledged by a crashed consumer
  (`STREAM_CLAIM_MIN_IDLE_MS` = 30s). Verified present and exercised by
  `tests/test_workers/test_outbox_publisher.py`. **Caveat: this fix covers the outbox path only.**
  `internal_trigger_installment`'s final-retry-exhausted notification
  (`payment.installment_failed`) still does a plain `redis.publish()`
  (`src/api/v1/payments.py:614`), and `src/events/listeners.py`'s inbound subscription to
  `order.cancelled` / `ledger.payment_collection_triggered` is also plain pub/sub with no stream
  fallback — if this service is down when Ledger publishes an overdue-installment trigger, that
  specific trigger is lost (the next sweep cycle will eventually re-trigger it, so this is bounded,
  not silent-forever, but it is not covered by the same durability fix as the main outbox).
- **`ENVIRONMENT` fail-open default — FIXED.** The HIGH finding (misconfigured/unset `ENVIRONMENT`
  silently enabling fake-success fallbacks) is resolved via `ALLOW_TEST_PAYMENT_FALLBACKS`
  (`src/config.py`): fallback behavior now requires **both** `ENVIRONMENT == "local"` **and** this
  explicit flag (`settings.test_payment_fallbacks_enabled`). Verified at every fallback call site —
  `src/services/jazzcash.py`, `src/services/safepay.py`, `src/services/raast.py`,
  `src/adapters/stripe_issuing.py`, `src/adapters/lithic.py`, and `require_internal_token` in
  `src/core/dependencies.py` (which now raises `503 INTERNAL_AUTH_NOT_CONFIGURED` instead of
  silently disabling internal auth) all gate on this flag, not a bare `ENVIRONMENT != "local"`
  check. `validate_critical_settings()` in `src/config.py` additionally refuses to boot if
  `ALLOW_TEST_PAYMENT_FALLBACKS=true` outside `ENVIRONMENT=="local"`. Stripe's webhook handler
  still has one residual soft-fail: if `STRIPE_WEBHOOK_SECRET` is unset **and**
  `test_payment_fallbacks_enabled` is true, it parses the payload without HMAC verification
  (`src/api/v1/webhooks.py:400-406`) — correctly gated, not a regression.
- **Webhook dedup keyed on gateway-stable id, not `SHA256(body+signature)` — FIXED.** The MEDIUM
  finding is resolved: `_dedupe_webhook` (`src/api/v1/webhooks.py`) now keys primarily on each
  gateway's own stable identifier (`gateway_txn_id`, `refund_reference`, `mandate_reference`, or
  Stripe's `evt_...` event id), falling back to the old body+signature hash only when a payload
  carries none of those. This means a legitimate retry with a re-signed timestamp or reordered
  fields is now correctly recognized as the same event instead of double-processing.
- **VCN issued at down-payment amount instead of order total — FIXED.** All three
  `webhooks.py` handlers (SafePay/JazzCash/Raast) and both queue-consumer paths
  (`payment_initiate_consumer.py`, `payment_webhook_consumer.py`) now re-fetch the order and call
  `VcnService.queue_issue(amount_pkr=order.total_amount)`, not the down-payment amount just
  confirmed. Before this fix, `issue_vcn`'s 5% price-drift check
  (comparing the requested amount against `order.total_amount`) rejected every real async-gateway
  down payment, so VCN issuance never succeeded outside the JazzCash sync path or dev-mode. Code
  comments at each call site document this was a live-tested bug, not a hypothetical.
- **`gateway.payment_confirmed` → Gateway callback is load-bearing and easy to silently break.**
  `VcnService.confirm_down_payment` looks up a matching Gateway-owned `PaymentTransaction` by
  `(order_id, transaction_type == "down_payment", status IN (initiated, pending))` to know which
  payment to tell Gateway to confirm. If that lookup finds nothing (e.g. a future direct
  integration that skips Gateway's own down-payment endpoint and calls this service's
  `/payments/down-payment` directly — see section 5), it only logs a warning; `Order.status` never
  advances past `CONTRACTS_SIGNED`. **Anything that initiates a down payment outside Gateway's own
  endpoint will silently strand the order** unless it also creates a compatible
  `PaymentTransaction` row first.
- **`PaymentTransaction.order_id` is always NULL from every write path in this service** — admin's
  `GET /admin/payments/transactions` works around it with a `Loan` outer-join fallback
  (`t.order_id if t.order_id is not None else loan.order_id`, `src/api/v1/admin.py:50-64`), but any
  new consumer reading `PaymentTransaction.order_id` directly (rather than through this endpoint or
  a similar join) will see `NULL` for every row created by `pay_installment`,
  `auto_collect_installment`, `internal_trigger_installment`, and the queue consumers — only
  `loan_id`/`installment_id` are set at those call sites.
- **VCN void doesn't guarantee the card is dead at the network.** `POST /payments/vcn/{id}/void`
  retries Stripe cancellation 3× and, on continued failure, marks the local row `voided` anyway and
  only logs an error (`src/api/v1/vcn.py:87-99`). A frontend showing "card voided" is showing the
  local DB state, not a confirmed guarantee that Stripe will decline further authorizations on that
  card — build any success messaging around `stripe_canceled` in the response, not just `status`.
- **Admin `/admin/payments/adjustments` only queues an event — does not move money.** It emits
  `payment.adjustment_requested` via the outbox and returns `{status: "queued"}`; there is no
  `PaymentTransaction` write and this read did not trace a confirmed downstream consumer of that
  event name. **Do not build admin UI copy implying an adjustment takes effect immediately** —
  verify a live consumer exists (grep `payment.adjustment_requested` across `ledger-service`)
  before promising synchronous effect.
- **`/admin/payments/reconciliation/trigger` is fire-and-forget** — the response returns before the
  `asyncio.create_task`-launched reconciliation job finishes; there is no endpoint to poll its
  completion. An admin dashboard needs to re-query `/admin/payments/transactions` or a
  reconciliation report endpoint afterward, not expect this call's response to carry a result.
- **Mandate setup for JazzCash is asserted but not necessarily backed.** `setup_mandate`
  (`src/api/v1/mandates.py`) accepts `gateway in ["raast", "jazzcash"]` and 400s if the selected
  adapter's client lacks a `setup_mandate` method — this read did not verify a real
  `JazzCashClient.setup_mandate` implementation exists with the same completeness as Raast's; treat
  JazzCash mandate setup as unverified until confirmed against the adapter directly if a frontend
  needs it.
- **`/health` is unconditional** (always 200, even with DB/Redis down) — point actual readiness
  monitoring/load-balancer health checks at `/health/ready`, which does check DB/Redis/Stripe.

## 5. Auth & Headers

**A new frontend should never call Payment Orchestrator directly, in any environment.** This is
the single most important integration fact for this service, and it is stronger here than for any
other backend service in this fleet given what this service touches (live PAN/CVV, four payment
gateway credentials):

- `infra/k8s/base/network-policies/13-payment-orchestrator.yaml` — ingress restricted to pods
  labeled `app: gateway` on port 8000 only; nothing else in the cluster can reach it, and there is
  no public ingress route to it at all (confirmed no rule in `overlays/*/ingress.yaml` targets this
  service).
- **But Gateway's own source has no HTTP client pointed at Payment Orchestrator anywhere** —
  confirmed by grep across `apps/gateway/src` for any `PAYMENT_ORCHESTRATOR_URL`-style config or
  outbound call. The network-policy YAML's own comment describes Gateway calling this service
  "over cluster DNS with a signed X-Internal-Token" for down-payment/installment flows, but that
  description does not match what Gateway's code actually does today — same pattern as the
  credit-engine audit found for that service's HTTP API.
- **What actually happens in production**, confirmed end-to-end by reading both services:
  1. Gateway's own customer-facing routes (`apps/gateway/src/api/v1/payments.py`:
     `POST /api/v1/payments/down-payment`, `POST /api/v1/payments/installment/{id}/pay`,
     `POST /api/v1/payments/refund/{order_id}`, `POST /api/v1/payments/vcn/issue`) are what a
     frontend actually calls. Each writes its own `PaymentTransaction`/`Order` state, then `lpush`es
     a job onto a Redis list (`sk:queue:payment_initiate` or `sk:queue:vcn_issue`) — it does not
     call Payment Orchestrator over HTTP.
  2. Payment Orchestrator's `PaymentInitiateConsumer` and `VcnIssueWorker`
     (`src/workers/payment_initiate_consumer.py`, `src/workers/vcn_issue_worker.py`), started
     as background asyncio tasks inside this service's own FastAPI process (`src/main.py`
     lifespan), pop those jobs directly — in-process function calls into
     `GatewayAdapterFactory`/`VcnService`, not HTTP.
  3. Vendor webhooks (JazzCash/SafePay/Stripe) hit **Gateway's** public
     `POST /api/v1/webhooks/payment/{gateway}` (Gateway is the only internet-reachable service),
     which verifies the vendor's HMAC and enqueues onto `sk:queue:payment_webhook`; Payment
     Orchestrator's `PaymentWebhookConsumer` (`src/workers/payment_webhook_consumer.py`) picks it
     up. **This service's own `/api/v1/webhooks/{gateway}` routes (section 2) do the same
     downstream processing and stay in the codebase for direct-integration/local testing, but per
     the network policy above they are not reachable from outside the cluster today** — a real
     vendor webhook cannot land on them directly.
  4. Payment Orchestrator talks back to Gateway exactly once in this flow: `OutboxPublisher`
     POSTs to Gateway's `POST /api/v1/internal/payments/{payment_id}/confirm` with header
     `X-Internal-Token: <INTERNAL_API_TOKEN>` when a `gateway.payment_confirmed` outbox event is
     processed — this is what actually advances `Order.status`.
  5. The full JWT-gated `/payments/*`, `/payments/vcn/*`, `/payments/mandates/*` API documented
     in section 2 is real, tested, and would work if called — but nothing calls it today except
     this service's own test suite. **If a new frontend team wants a live per-request payment API
     (rather than the queue-and-poll pattern above), the choice is either (a) keep building against
     Gateway's existing customer-facing routes — the actually-live path — or (b) add a proxy route
     on Gateway that forwards to this service's HTTP API, which does not exist today.**

**JWT shape required by this service's own routes:** RS256 against `settings.JWT_PUBLIC_KEY`
(same key Gateway signs with). Customer routes require `user_id`; admin routes require `admin_id`
**and** a `role` claim checked against `RequireRole`'s allowed-roles list per route (this service,
unlike credit-engine, does enforce per-route RBAC). There is no internal-service-token mode for
inbound customer/admin routes — only the explicitly `include_in_schema=False`
internal/auto-collect/decrypt routes accept `X-Internal-Token` instead of a JWT.

**Webhook signature schemes** (relevant to anyone building an admin view that surfaces
webhook/payment status, or debugging a stuck payment):

| Gateway | Header | Scheme |
|---|---|---|
| SafePay | `X-Safepay-Signature` | HMAC via `SafepayClient.verify_signature`, keyed off `SAFEPAY_WEBHOOK_SECRET` |
| JazzCash | `X-JazzCash-Signature` | HMAC via `JazzCashClient.verify_signature`, keyed off merchant credentials |
| Raast | `X-Raast-Signature` | HMAC via `RaastClient.verify_signature`, keyed off `RAAST_API_SECRET` |
| Stripe | `Stripe-Signature` | Native `stripe.Webhook.construct_event` against `STRIPE_WEBHOOK_SECRET` |

All four verify **before** dedup and before any DB read — an invalid signature always 401s
immediately (`INVALID_SIGNATURE`), never silently ignored, except under the explicitly-gated
`test_payment_fallbacks_enabled` local-dev bypass for Stripe noted in section 4.

**Internal-service auth:** `X-Internal-Token`, constant-time-compared
(`src/core/security.py::constant_time_compare`) against `settings.INTERNAL_API_TOKEN` — the same
shared secret convention every other internal service in this fleet uses (named
`INTERNAL_SERVICE_TOKEN` on Gateway's side). Used for: `/payments/internal/trigger-installment`,
`/payments/internal/installments/{id}/auto-collect`, `/internal/vcn/{order_id}/decrypt`, and (as
the outbound caller) `OutboxPublisher`'s call to Gateway's `/internal/payments/{id}/confirm`.
