# Product Service — Integration Reference

**Service path:** `apps/product-service/`
**Document date:** 2026-08-28
**Audience:** engineers building a new frontend/integration against this existing backend. This is not a security audit — it is a factual description of what the service does and how to call it, verified directly against the current source.

---

## 1. Service Purpose

Product Service has two distinct jobs. First, it turns a merchant product URL (Daraz, Amazon, Shopify/WooCommerce/BigCommerce/Magento storefronts, or arbitrary "CUSTOM" sites) into a normalized product record — the **UPO** (Universal Product Object) — with title, price, images, availability and variant data, and computes Murabaha (Shariah-compliant installment) pricing options against it. Second, once a customer has financed a purchase and a Virtual Card Number (VCN) has been issued, it runs a **fully autonomous Playwright buyer agent** that navigates the merchant's real checkout, fills the form, enters the VCN, and completes the purchase on the platform's behalf — no human or frontend drives this step by step. Every endpoint in this service other than customer-facing extraction/offer lookups is called by other backend services (principally the Gateway, which proxies customer/admin requests) using a shared internal token, not directly by a browser.

---

## 2. API Endpoint Catalog

All routes are mounted under `/api/v1`. There is no service-level OpenAPI consumer-facing distinction between "public" and "internal" routers — auth is enforced per-route via FastAPI dependencies (see §6). Every route below was read directly from `src/api/v1/*.py`.

### 2.1 `products.py` — prefix `/api/v1/products`

```
POST   /products/extract
```
Submit a raw product URL for extraction. Body (`ExtractRequest`): `raw_url` (string, 8–2048 chars), `order_id` (optional int), `correlation_id` (optional string, max 128 chars). Auth: `get_current_user_id` — requires `x-internal-service-token` header; `x-user-id` header is trusted only alongside that token (so this is safe to expose through the Gateway but not directly to browsers). Response (`ExtractResponse`): `status` is either `"completed"` (product already cached/known or extraction resolved synchronously — `upo` is populated) or `"extracting"` (async job queued or a same-URL extraction already in flight — `job_id` is populated, `upo` is null). A `meta` dict may carry `{"cache_hit": true|false}` or `{"hitl_required": true}`. Rate-limited per user/IP via `EXTRACT_RATE_LIMIT_PER_MINUTE` (default 10/min); a 409 `EXTRACTION_IN_PROGRESS` is possible if a same-URL lock can't be acquired and no product/job exists yet.

```
GET    /products/jobs/{job_id}
```
Poll an extraction job. Auth: `require_user_id` (same internal-token + `x-user-id` scheme, but the user ID is mandatory here). Response (`JobStatusResponse`): `job_id`, `status` (one of `queued`, `running`, `retrying`, `completed`, `failed`), `upo` (populated once `status == completed`), `error_code`/`error_message` on failure. Returns 404 `JOB_NOT_FOUND` if the job doesn't exist **or** belongs to a different user — deliberately indistinguishable, to prevent job-ID enumeration.

**This is the polling pattern a frontend must implement**: call `POST /products/extract`; if `status == "extracting"`, poll `GET /products/jobs/{job_id}` (there is no SSE/websocket for extraction, unlike checkout — see §2.2) until `status` is `completed` or `failed`.

```
GET    /products             (list_user_products)
```
Auth: `require_user_id`. Query: `limit` (≤100, default 20), `offset`, `cursor`. Lists products this user has previously extracted (joined via `ScrapingJob.user_id`). Response (`SearchResponse`): `items` (`SearchItem`: `product_id`, `name`, `canonical_url`, `currency`, `cost_price`, `sale_price`), `total`, `next_cursor`.

```
GET    /products/search
```
No auth dependency. Query: `q` (required, min 2 chars), `limit` (≤100), `cursor`. Full-text/keyword search across all products (not scoped to a user). Same `SearchResponse` shape.

```
GET    /products/{upo_id}
```
No auth dependency. Returns `ProductDetailResponse` — the full UPO shape (§3) plus `scraping_jobs` (last 5, `{job_id, status}`) and `checkout_executions` (last 5, `{execution_id, status}`).

```
POST   /products/{upo_id}/refresh
```
Auth: `require_service_token` (internal only). Body: `{"reason": str|null}`. Forces a re-extraction of an already-known product (invalidates cache, resets `extraction_method`/`extraction_confidence`, re-queues onto the scraping queue).

```
GET    /products/{upo_id}/offer
```
Auth: `require_service_token` (internal only — the Gateway calls this on the customer's behalf; it is **not** meant to be hit directly from a browser). Query: `plan_months` (optional int — omit to get all three plans; pass `3`/`6`/`12` for exactly one), `down_payment_pct` (decimal, default `30.0`). Returns 422 `OUT_OF_STOCK` if the product isn't purchasable, 503 `SHARIAH_APPROVAL_REQUIRED` if the Murabaha markup structure has no configured Shariah-board approval reference (see §3), 400 `INVALID_DOWN_PAYMENT_PERCENTAGE` if `down_payment_pct` falls outside the admin-configured `min_down_payment_pct`/`max_down_payment_pct` system parameters (defaults 25–40%). Response is `MultipleOffersResponse` (`financing_offers`: list of 3 `FinancingOffer` objects) when `plan_months` is omitted, or `SingleOfferResponse` (single `financing_offer`) when it's given. See §3 for the `FinancingOffer` field breakdown.

```
GET    /products/{upo_id}/price-history
```
Auth: `require_service_token`. Returns `PriceHistoryResponse`: list of `{old_price, new_price, changed_at}`.

### 2.2 `agent.py` — prefix `/api/v1/products/agent` (checkout automation)

All routes here require `require_service_token` (internal only). This is the interface the Gateway (and, if built, an admin dashboard) uses to track and control checkout jobs — a frontend should never call these directly, and should never expect to drive the checkout step-by-step (see §4).

```
GET    /products/agent/order/{order_id}/latest
```
Looks up the most recent `PurchaseExecution` for an order (there is no direct order→job index elsewhere; this is the bridge from an order ID to a job UUID). Returns `AgentLatestExecutionResponse`: `job_id`, `status`, `step_reached`, `merchant_order_id`. 404 `EXECUTION_NOT_FOUND` if none exists yet.

```
POST   /products/agent/queue-job
```
Body (`AgentQueueRequest`): `order_id` (int, required), `vcn_id` (int, required), `correlation_id` (optional), `force_failure` (bool, default false — test-only forced-failure switch). Enqueues a checkout job onto the `sk:queue:checkout` Redis list. Idempotent: if a job already exists for that `(order_id, vcn_id)` pair in `queued`/`running`/`pending_verification`, returns the existing one instead of duplicating. Response: `{status: "queued", job_id, estimated_completion_seconds: 45}`.

```
GET    /products/agent/job/{job_id}/stream
```
Server-Sent Events stream (`text/event-stream`). Emits one `data:` event per step transition (`{step, status, timestamp}`) and a final `{done: true}` when the job reaches a terminal status (`succeeded`, `failed`, `hitl_escalated`, `cancelled`). Polls the DB every 0.5s internally, capped at 120 iterations (~60s) before the generator ends on its own even if not terminal — a caller should reconnect or fall back to polling `GET /order/{order_id}/latest` if it needs to keep watching past that.

```
POST   /products/agent/job/{job_id}/cancel
```
Marks a `queued`/`running`/`pending_verification` job `cancelled`, removes it from the Redis queue if still queued, and publishes a `vcn.void` event so Payment Orchestrator releases the card. If the job is already mid-Playwright-run, the running worker itself checks for this cancellation between steps and unwinds (see §4 — this is a real interrupt, not just a DB flag).

```
GET    /products/agent/job/{job_id}/screenshot
```
302-redirects to the S3 URL of the job's receipt/failure screenshot (`receipt_screenshot_s3` preferred, falls back to `screenshot_s3`). 404 `SCREENSHOT_NOT_FOUND` if neither exists.

### 2.3 `admin.py` — prefix `/api/v1/admin` (all internal-only, `require_service_token`)

Product/catalog management:
```
GET    /admin/products                          — cursor-paginated product list
GET    /admin/products/{uuid}                    — detail + last 20 scraping jobs + linked checkout executions
PATCH  /admin/products/{uuid}                     — edit name/url/canonical_url/platform/cost_price/sale_price/stock_status/in_stock/extraction_method; audit-logged
POST   /admin/products/{uuid}/prohibit            — mark prohibited with a reason; audit-logged
POST   /admin/products/{uuid}/unpromote           — forces extraction_confidence to 0.10 (demotes a bad extraction)
DELETE /admin/products/{uuid}                     — soft-delete; audit-logged
```

Checkout execution management:
```
GET    /admin/executions                          — cursor-paginated PurchaseExecution list, optional product_id filter
POST   /admin/executions/{uuid}/retry             — see below
```
`retry` behavior: 409 if already `succeeded`. If `status == "running"`, it now checks `ExecutionReaperService.is_stuck()` (running longer than `CHECKOUT_STUCK_RUNNING_TIMEOUT_SECONDS`, default 900s) — if stuck, it reaps it (marks failed/hitl_escalated) and falls through to requeue; if genuinely still in-flight, returns `{status: "running"}` without requeuing. Otherwise requeues onto the checkout queue.

Scraping job visibility, prohibited-category CRUD, merchant management, and queue/DLQ operations:
```
GET    /admin/scraping-jobs                       — cursor-paginated, optional status filter
GET    /admin/prohibited-categories                — list
POST   /admin/prohibited-categories                — upsert by category_name; invalidates the negative-result cache
DELETE /admin/prohibited-categories/{id}           — delete; invalidates cache
GET    /admin/merchants                            — cursor-paginated, includes per-merchant product_count
GET    /admin/merchants/{domain}                   — detail
POST   /admin/merchants/{domain}/block?reason=...  — blocks a merchant domain; audit-logged
GET    /admin/queue-stats                          — checkout/scraping queue depths + DLQ depths + up to 10 DLQ entries each (pan/cvv keys stripped defensively before response, even though the checkout queue payload no longer carries card data at all)
POST   /admin/dlq/{queue_name}/reprocess/{index}   — requeue one DLQ entry by index
DELETE /admin/dlq/{queue_name}/purge               — purge a DLQ (checkout|scraping)
GET    /admin/analytics/extraction-stats           — ScrapingJob counts grouped by status
POST   /admin/prohibited-categories/sync           — no-op today beyond invalidating the negative-result cache (returns {"status":"synced","count":0})
GET    /admin/extraction-waterfall/config          — static description of the 4 tiers (see §3)
```

### 2.4 `health.py` — no auth, used by orchestration/load balancers
```
GET    /health          — {status, service, redis} — "degraded" if Redis is unreachable
GET    /health/live     — always {"status": "ok"} if the process is up
GET    /health/ready    — 503 if DB down, Redis down, or the event-listener background task has died; also reports checkout/scraping queue depth and DLQ pressure
```
There is also a bare `GET /metrics` (Prometheus, no `/api` prefix) registered directly in `main.py`.

---

## 3. Extraction & Pricing Flow

### 3.1 The extraction waterfall

`ExtractionWaterfallService.extract()` tries tiers in order until one produces a result that clears its confidence threshold; platform detection decides the tier order:

| Tier | Source | Notes |
|---|---|---|
| Tier 1 | Rye API | Skipped unless `FEATURE_RYE_ENABLED` and a real `RYE_API_KEY` are set (off by default — paid tier). Skipped entirely for Daraz. |
| Tier 2A | Violet API | Skipped for Daraz; skipped without a `VIOLET_API_KEY`. |
| Tier 2B | Direct HTML fetch + JSON-LD/OpenGraph/meta-tag parsing | Always attempted for WooCommerce/BigCommerce/Magento/Daraz first (before Playwright); confidence varies by which parse strategy succeeded (0.85 JSON-LD / 0.65 OpenGraph / 0.40 meta tags). |
| Tier 3 | Playwright + LLM (Groq primary, OpenAI fallback if enabled) | Last resort; renders the page, distills visible text, asks an LLM to structure it into JSON. Cross-checks its price against the best price seen from any earlier (even below-threshold) tier — rejects if the drift exceeds `TIER3_PRICE_CROSSCHECK_TOLERANCE_PCT` (35% by default), to catch a hallucinated/manipulated LLM price before it becomes the purchase cost basis. |

Per-tier confidence thresholds default to 0.90/0.80/0.60/`EXTRACTION_CONFIDENCE_THRESHOLD` (0.70) for tiers 1/2A/2B/3 respectively. A tier that fails 5 times in a rolling window trips a Redis circuit breaker (2-minute tier-wide block, or 5-minute domain-specific block) so a broken upstream doesn't get hammered on every request. `SOCIAL_COMMERCE` platform URLs (Instagram, etc.) skip the waterfall entirely and go straight to HITL/manual — there's no structured page to extract from.

If every tier fails, the job either resolves to `hitl_required` (queued for manual concierge purchase, if `FEATURE_HITL_ESCALATION` is on — default on) or a hard `failed`.

Async retries (`scraping_worker.py`) use exponential backoff: `EXTRACTION_RETRY_BACKOFF_BASE_SECONDS * 2^(attempt-1)`, capped at `EXTRACTION_RETRY_BACKOFF_MAX_SECONDS`, quadrupled as the base delay when the failure was tagged `RATE_LIMITED` (an LLM-provider 429), plus up to 25% jitter.

### 3.2 What a frontend gets back — the UPO shape

`UpoResponse` (returned inline from `/extract` when synchronous, or from `/jobs/{id}` and `/products/{upo_id}` once resolved):

```
product_id, source_url, platform, extraction_method, extraction_confidence,
availability: "in_stock" | "out_of_stock" | "limited" | "unknown",
is_purchasable: bool,
meta: { title, brand, description, images: [url,...] },
pricing: { amount, currency },
variants: [ { option_name, options: [{label, value, is_available}] }, ... ],
shipping: { estimated_cost, estimated_days, ships_to_pakistan } | null
```
`is_purchasable` is `in_stock AND NOT is_prohibited` — check this before letting a user proceed to financing, not just `availability`.

### 3.3 Murabaha pricing — three fixed plans

Markup is tiered, not a flat rate: **3-month plan 2.5%, 6-month plan 7.0%, 12-month plan 12.0%** total markup on cost price (documented in `pricing_service.py` as the nominal-total equivalent of a 4%-p.a. disclosed rate). `calculate_offer()` / `calculate_multiple_offers()` produce a `FinancingOffer` per plan:

```
plan_months, profit_rate_pct, cost_price, profit_amount, total_repayable,
down_payment_amount, installment_count, installment_amount
```
(the service internally also computes `bi_weekly_installment_count`/`bi_weekly_amount`, but those two fields are **not** in the `FinancingOffer` Pydantic schema returned over the API — they're dropped at serialization. If bi-weekly display is needed, it has to be derived client-side or the schema extended.)

**Important gate**: `PricingService.is_shariah_approved` is `False` unless both `SHARIAH_MARKUP_APPROVAL_REFERENCE` and `SHARIAH_MARKUP_APPROVAL_DATE` are configured — and unlike the older version of this code, `GET /{upo_id}/offer` now actually **enforces** this (503 `SHARIAH_APPROVAL_REQUIRED` if unset), rather than just exposing it as an unenforced status flag. A fresh environment with no Shariah-board reference configured will refuse to generate offers at all until that's set.

Down-payment percentage is bounds-checked against the `min_down_payment_pct`/`max_down_payment_pct` system parameters (DB-backed, admin-configurable via Gateway; falls back to 25%/40% if unset).

---

## 4. Checkout Automation Flow

This is a backend-driven Playwright agent, not a frontend-orchestrated flow. A frontend's role is limited to: triggering checkout indirectly (via the order/payment flow through the Gateway, which calls `POST /products/agent/queue-job` once a VCN is issued), and **observing** state — polling or streaming job status, and optionally showing a receipt screenshot. There is no API for a frontend to tell the agent what to click, retry a specific step, or supply merchant-site credentials interactively.

### 4.1 `PurchaseExecution` states

```
queued → running → succeeded
                  → pending_verification → succeeded | hitl_escalated | failed
                  → hitl_escalated (on failure, if HITL escalation is on)
                  → failed (on failure, if HITL escalation is off)
        (at any point) → cancelled
```
`step_reached` (visible via the SSE stream and `GET /order/{id}/latest`) walks through: `navigating → variant_selection → add_to_cart → price_drift_check → guest_checkout → form_fill → shipping_selection → payment_injection → review_order_page → order_submitted → order_confirmed → receipt_captured`, with `pending_verification` and `checkout_uncertain` as branch states after the merchant page confirms (or fails to clearly confirm) the order.

`succeeded` is not actually final in the sense of "money moved" — after the Playwright run reports success, the execution moves to `pending_verification` and a separate `vcn_verification_worker.py` polls (with backoff) for a real Stripe/VCN charge-confirmation signal before the order is considered truly `succeeded`. If that verification times out, the job becomes `hitl_escalated` (or `failed` if HITL is off).

### 4.2 Cancellation and crash recovery — both now real

- **Cancellation** (`POST /products/agent/job/{job_id}/cancel` or an `order.cancelled` event) marks the DB row `cancelled` from a separate session while the checkout worker may still be mid-Playwright-run in a different process. The worker's `process_job` re-checks the persisted status **between every step** (via its `emit_step` callback) and again immediately before the final "succeeded" commit, raising `CheckoutCancelledError` to unwind if it sees `cancelled` — so a cancelled order's in-flight purchase is actually interrupted rather than completing and clobbering the cancelled state.
- **Worker crash recovery**: if a checkout-worker process dies mid-job (OOM, deploy, host failure), the row is left at `running` with no terminal status ever written. `ExecutionReaperService`/`ExecutionReaperWorker` sweep on an interval (`EXECUTION_REAPER_INTERVAL_SECONDS`, default 300s) for rows stuck at `running` longer than `CHECKOUT_STUCK_RUNNING_TIMEOUT_SECONDS` (default 900s) and mark them `failed`/`hitl_escalated`. The admin retry endpoint also performs this check just-in-time, so a stuck row doesn't have to wait for the next scheduled sweep.

### 4.3 Card data handling

The checkout job payload placed on the Redis queue never carries PAN/CVV. The worker fetches plaintext card credentials just-in-time from Payment Orchestrator's internal decrypt endpoint (`GET {PAYMENT_ORCHESTRATOR_URL}/api/v1/payments/internal/vcn/{order_id}/decrypt`) immediately before typing them into the merchant's payment form. Once that "payment injection" step begins, the self-healing (LLM screenshot-based selector recovery) subsystem is permanently disabled for the remainder of that job — see §5.

---

## 5. Known Gaps & Caveats Relevant to Integration

The service's own `docs/PRODUCTION_GAPS_REPORT_2026-08.md` (dated the same day as this document) listed 12 CRITICAL and several HIGH findings for this service. Each was checked directly against the current code for this rewrite:

**Fixed, confirmed in code:**

- **SSRF / DNS-rebinding at fetch time (was CRITICAL #8).** The report's original finding was that `url_normalizer.py` validated a URL's resolved IP only at `POST /products/extract` submission time, while the async worker that actually fetches the page later did a fresh, unprotected DNS lookup — letting an attacker rebind their domain to a private/metadata IP (e.g. `169.254.169.254`) between submission and fetch. This is now closed: `url_normalizer.py` exposes `resolve_pinned_request()` / `ensure_fetch_target_is_safe()` as fetch-time re-validation entry points, and both fetchers call them immediately before connecting — `html_scraper.py` pins the actual httpx connection to the freshly-validated IP (with SNI/Host header preserved), and `playwright_agent.py` re-validates immediately before `page.goto()` (it can't pin Chromium's own connection the way httpx can, so a narrower TOCTOU window remains between that check and Chromium's internal DNS lookup — documented in-code as an accepted residual limitation, not a full fix). Both have dedicated regression tests (`tests/test_extractors/test_html_scraper.py::test_fetch_and_parse_rejects_dns_rebound_to_private_ip`, `tests/test_extractors/test_playwright_agent.py::test_extract_rejects_dns_rebound_to_private_ip_at_fetch_time`).
- **Cardholder data to OpenAI (was CRITICAL #9).** The report's finding was that `self_healing.py`'s selector-recovery screenshot (sent to `gpt-4o-mini` on any unrecognized selector) could fire on steps after live PAN/CVV had already been typed into the page, with no redaction. `SelfHealingService` now has a `payment_data_injected` flag, set by `CheckoutFormFiller` right as the "Payment Injection" step begins (before any card field is typed) via `mark_payment_data_injected()`. Both self-healing entry points (`suggest_selector`, `suggest_form_field_selector`) check this flag first and return `None` — refusing to screenshot — for the rest of that job's lifetime, fail-closed. **Caveat**: no dedicated unit test for this specific lockout was found anywhere under `apps/product-service/tests/` (searched for `SelfHealingService`, `payment_data_injected`, `mark_payment_data_injected` — no matches) despite the gaps report's changelog claiming one was added. The fix itself is real and correctly implemented in code; the test-coverage claim could not be verified.
- **`prohibited_merchant_domains` table / poisoned-transaction bug.** `ProhibitedCheckerService.check_url()` queried a table that no migration had ever created; on real Postgres (not SQLite, which unit tests run against) a failed statement inside an open transaction poisoned every subsequent query on that connection, surfacing as a 500 on every `POST /products/extract` call. Migration `088_add_prohibited_merchant_domains_table.py` creates the table, and the query is now wrapped in `db.begin_nested()` (a SAVEPOINT) so a failure there can't cascade into the rest of the request.
- **Checkout worker crash recovery** — see §4.2.
- **Order cancellation mid-checkout** — see §4.2.
- **Extraction retry backoff** — see §3.1; exponential backoff with jitter now exists, including a longer initial delay specifically for LLM-provider 429s.
- **`GET /products/{upo_id}/offer` auth** — the gaps report listed this as having no auth, inconsistent with sibling endpoints. Current code has `_: None = Depends(require_service_token)` on this route, consistent with the rest of the file.

**Open / by design:**

- **`E2E_ALLOWED_FETCH_HOSTS`** (`src/config.py`) is a test-only SSRF allowlist for the docker-compose E2E suite to reach a mock-merchant fixture container that legitimately resolves to a private IP on the compose bridge network. It is empty by default in every real environment (only `docker-compose.e2e.yml` sets it) and only exempts an exact allowlisted hostname from the private-IP rejection — every other host is still fully checked. Not a production security control; do not rely on or extend it for anything beyond local E2E testing.
- **Bi-weekly installment fields are computed but not exposed** — see §3.3.
- **No cross-service or end-to-end workflow test exercises the full extraction→offer→checkout chain** as one connected flow; per-service unit/integration tests are strong (174 passed / 2 failed in this service's own suite as of this check — see below), but nothing brings up Product Service together with Gateway/Payment Orchestrator and runs a real order through it.
- **Test suite status**: running `pytest -q` in `apps/product-service` produces **174 passed, 2 failed**. The 2 failures (`test_extraction_circuit_breaker_trips`, `test_vcn_verifier_timeout_comes_from_settings`) are pre-existing and unrelated to any of the fixes above — confirmed present in the codebase and consistent with the gaps report's own note that these were isolated via an A/B `git stash` comparison against pre-fix code.

---

## 6. Auth & Headers

There are three trust tiers in this service, all enforced by FastAPI `Depends()`, not by a gateway-level proxy rule — reading the route list in §2 for the actual dependency on each endpoint is the source of truth:

- **`require_service_token`** (`src/core/dependencies.py`) — checks header `x-internal-service-token` against `INTERNAL_SERVICE_TOKEN` with `hmac.compare_digest`. This is the internal-only tier: all of `admin.py`, all of `agent.py`, and several `products.py` routes (`refresh`, `offer`, `price-history`) require it. **None of these are safe to expose directly to a browser** — they carry no per-user authorization beyond the shared secret.
- **`get_current_user_id` / `require_user_id`** — requires the same `x-internal-service-token` header *plus* trusts an `x-user-id` header forwarded by the caller (i.e., the Gateway, which has already authenticated the actual human via its own JWT/session layer). `get_current_user_id` returns `None` if `x-user-id` is absent (used where a user context is optional); `require_user_id` 401s if it's missing. This is the tier `POST /products/extract`, `GET /products/jobs/{id}`, and `GET /products` (list) use — effectively "customer-facing, but only reachable via the Gateway, which is the actual authentication boundary."
- **`get_current_admin_id`** — same internal-token requirement, plus an optional `x-admin-user-id` header used purely for audit-log attribution (who performed this admin action); absent header logs the action as unattributed rather than guessing. Used on the admin `patch`/`prohibit`/`delete`/`block` mutation endpoints for audit trail purposes — it does not itself gate access (that's still `require_service_token`); the Gateway's own RBAC layer is what actually decides whether an admin may call these routes in the first place.
- **No-auth routes**: `GET /products/search`, `GET /products/{upo_id}`, and all of `health.py` / `/metrics`. These return only already-public-once-extracted product data or liveness info, not anything customer- or order-specific.

Every route in this service assumes it sits behind the Gateway and is never reachable directly from the public internet — there is no independent rate limiting or IP allowlisting at this layer beyond the per-user/IP extraction rate limit (`EXTRACT_RATE_LIMIT_PER_MINUTE`) and the Redis circuit breakers on extraction tiers.
