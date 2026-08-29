# Notification Service — Integration Reference

**Service path:** `apps/notification-service/`
**Last verified against source:** 2026-08-28
**Test suite result (this run):** `109 passed, 0 failed` (114 warnings — Pydantic v2 deprecation notices + a few harmless "coroutine never awaited" warnings from `AsyncMock` in unit tests, not runtime bugs)

This document replaces the previous version of this file, which contained an invented readiness percentage and an incomplete endpoint list. Everything below was verified by reading the current source directly: `src/main.py`, `src/config.py`, `src/api/routes.py`, all six files under `src/api/v1/`, `src/core/dependencies.py`, `src/services/*`, `src/dispatchers/*`, `src/workers/*`, and the corresponding `sk_shared` models.

---

## 1. Service Purpose

Notification Service owns two distinct jobs behind one FastAPI app: (1) **multi-channel notification dispatch** (SMS, WhatsApp, push, email) for every customer-facing event in the platform — OTPs, KYC results, contract signing, payments, billing reminders, delivery updates — driven by a Redis pub/sub listener plus an internal HTTP API other services call directly; and (2) **shipment tracking** via AfterShip, including shipment registration, a customer status/history endpoint, and an AfterShip delivery webhook. It sits downstream of every other microservice: Gateway, Product Service, Credit Engine, Payment Orchestrator, and Ledger Service all either publish Redis events this service subscribes to, or call its internal endpoints directly (Gateway does both, for OTPs and for admin routes). It does not originate any business decision — it only renders and delivers messages about decisions made elsewhere, and mirrors shipment status onto the `Shipment`/`TrackingEvent` tables.

All four background workers (notification consumer, reminder sweep, retry sweep, scheduled-notification sweep) now run as in-process `asyncio` tasks started in `src/main.py`'s FastAPI `lifespan`, alongside the Redis pub/sub event listener. Previously these existed only as standalone `python -m` entry points with nothing in docker-compose or Kubernetes ever invoking them — meaning notifications were created in the DB but never actually dispatched, and reminder/retry/scheduled sweeps never ran. That gap is fixed as of the current code: as long as the service process is up, dispatch, retry, and reminder logic all run.

---

## 2. API Endpoint Catalog

Base path: `/api/v1/...` for everything except `GET /health`, `GET /api/v1/health/live`, `GET /api/v1/health/ready`, and `GET /metrics` (Prometheus, mounted as a sub-app).

### 2.1 Customer Endpoints — `src/api/v1/notifications.py`, prefix `/api/v1/notifications`

Auth: `Depends(get_current_user_id)` — reads an `X-User-Id` integer header. **This header is not cryptographically verified by this service** — see Section 5 for what that means for direct frontend access.

| Method & Path | Request body | Response body | Purpose |
|---|---|---|---|
| `GET /` | query: `page`, `page_size` (1-100), `unread_only`, `category` | `{items: [{id, title, body, category, priority, is_read, created_at, source_event, source_reference}], total, page, page_size, unread_count}` | Paginated notification inbox for the current user |
| `POST /{notification_id}/read` | — | `{status: "ok"}` (404 `NOTIFICATION_NOT_FOUND` if not this user's) | Mark one notification read |
| `POST /read-all` | — | `{status: "ok", marked_read: <count>}` | Mark all unread notifications read |
| `GET /unread-count` | — | `{unread_count: <int>}` | Badge count |
| `GET /preferences` | — | `{preferences: [{category, sms_enabled, whatsapp_enabled, push_enabled, email_enabled, is_globally_unsubscribed, ...raw NotificationPreference row fields}]}` | Per-category channel preferences. Note: returns raw ORM rows (no `response_model` binding to `NotificationPreferenceResponse`'s richer schema with `category_label`/`is_mandatory` — those fields are defined in `src/schemas/notifications.py` but not actually populated here) |
| `PUT /preferences` | `{preferences: [{category, sms_enabled?, whatsapp_enabled?, push_enabled?, email_enabled?}]}` | `{status: "ok", updated: <count>}` | Upsert channel preferences per category. `auth` and `compliance` categories are silently skipped (non-opt-out) |
| `POST /unsubscribe` | — | `{status: "unsubscribed", message: "..."}` | Global unsubscribe from all non-essential (non-`auth`/`compliance`) notifications |

### 2.2 Internal (Service-to-Service) Endpoints — `src/api/v1/notifications.py`, prefix `/api/v1/internal/notifications`

Auth: `Depends(require_internal_key)` — `X-Internal-Key` header, constant-time-compared against `settings.INTERNAL_API_KEY`.

| Method & Path | Request body | Response body | Purpose |
|---|---|---|---|
| `POST /send` | `{user_id, event_type, template_vars, idempotency_key, source_reference?, priority?, channels?}` | `{status: "queued", notification_id}` | Generic event-driven notification. Channels/priority default from `EVENT_CHANNEL_MATRIX` in `notification_service.py` keyed by `event_type` if not overridden |
| `POST /otp` | `{phone, otp_code, purpose, expires_in_seconds?, channels?}` | `{status: "sent", notification_id}` or 429 with `{detail: "TOO_MANY_OTP_REQUESTS"}` | Dedicated OTP path — bypasses user preferences and the normal queue, dispatches synchronously in-request. Rate-limited per phone (default 5/hour, 20/day). This is the endpoint Gateway calls for every OTP flow (registration, login resend, password reset, contract signing) |
| `POST /bulk` | `{event_type, notifications: [{user_id, template_vars, idempotency_key, source_reference?}]}` | `{accepted, skipped_duplicate, failed, queued_notification_ids}` | Bulk creation, used by scheduled/reminder sweeps and any bulk campaign push |

### 2.3 Admin Endpoints — `src/api/v1/admin_notifications.py`, prefix `/api/v1/admin/notifications`

Auth: `require_permissions([...])` — reads `X-Admin-Assertion` header, an HMAC-signed short-lived assertion minted by Gateway (see Section 5), not a raw role/permission header.

| Method & Path | Permission required | Request body | Response body | Purpose |
|---|---|---|---|---|
| `GET /` | `admin:notifications:read` | query: `page`, `page_size`, `user_id?`, `status?` | `{items: [<raw Notification ORM rows>], total}` | Admin notification list/search. No `response_model` — returns raw SQLAlchemy rows, not the richer `AdminNotificationListResponse` schema defined in `schemas/notifications.py` (that schema exists but is unused here) |
| `GET /stats` | `admin:notifications:read` | — | `{notifications: {<status>: count}, dispatches: {<status>: count}}` | Aggregate counts by `Notification.status` and `NotificationDispatch.status` |
| `GET /dlq` | `admin:notifications:write` | query implicit: first 100 items | `[<parsed DLQ JSON entries>]` | Peek at the dead-letter queue (Redis list `sk:queue:notifications:dlq`) |
| `POST /retry/{notification_id}` | `admin:notifications:write` | — | `{status: "re-queued"}` (404 if notification not found) | Reset one notification's DLQ'd dispatch rows to `pending`, re-enqueue to the main queue |
| `POST /dlq/retry-all` | `admin:notifications:write` | — | `{status: "ok", requeued_count}` | Re-enqueue every DLQ entry's notification and clear the whole DLQ key |
| `DELETE /dlq/purge` | `admin:notifications:write` | — | `{status: "ok"}` | Delete the DLQ key outright — no re-queue |
| `GET /scheduled` | `admin:notifications:read` | — | list of `ScheduledNotification` rows not yet fired | View pending scheduled notifications |
| `DELETE /scheduled/{scheduled_id}` | `admin:notifications:write` | — | `{status: "cancelled"}` (400 `ALREADY_FIRED` if already sent) | Cancel a scheduled notification before it fires |

### 2.4 Tracking Endpoints — `src/api/v1/tracking.py`, prefix `/api/v1/tracking`

| Method & Path | Auth | Request body | Response body | Purpose |
|---|---|---|---|---|
| `POST /register` | `require_internal_key` (`X-Internal-Key`) | `{order_id, tracking_number, courier_code}` | `{shipment_id, aftership_tracking_id, status}` | Register a shipment for an order with AfterShip. Idempotent — returns the existing `Shipment` if one already exists for the order. 422 `INVALID_COURIER_CODE` if the courier code isn't a known active `Courier` row |
| `GET /{order_id}` | `get_current_user_id` (`X-User-Id` header) | — | `{order_id, courier, tracking_number, aftership_tracking_id, status, estimated_delivery, actual_delivery, events: [{time, description, location, event_code}]}` | Full shipment status + event history for one order. 404 `SHIPMENT_NOT_FOUND` if no shipment row exists yet |

### 2.5 Admin Tracking — `src/api/v1/admin_tracking.py`, prefix `/api/v1/admin/tracking`

Auth: `require_operations_manager` — same signed `X-Admin-Assertion` mechanism, but hardcoded to require `role == "operations_manager"` specifically (not a generic permission check like `admin_notifications.py` uses).

| Method & Path | Response body | Purpose |
|---|---|---|
| `GET /issues` | `{issues: [{order_id, customer_name, courier, tracking_number, issue_type, days_in_state}], total}` | Ops dashboard: shipments stuck in `delivery_attempted`, `delivery_exception`, `returned`, or `in_transit` for more than 7 days |

### 2.6 Webhook Endpoints — `src/api/v1/webhooks.py`, prefix `/api/v1/webhooks` — public, provider-signed

| Method & Path | Signature verification | Request body | Response | Purpose |
|---|---|---|---|---|
| `POST /aftership` | `X-Aftership-Hmac-Sha256` header, HMAC-SHA256 against `AFTERSHIP_WEBHOOK_SECRET`. **Always enforced** (empty secret → verification fails closed) | AfterShip tracking-update payload | `{received: true}` | Shipment status/checkpoint updates. Deduplicated via a Redis key hashing tracking id + tag + last checkpoint time |
| `POST /sendgrid` | `X-Twilio-Email-Event-Webhook-Signature` + `-Timestamp` headers, ECDSA-P256 verification, only enforced **if** `SENDGRID_WEBHOOK_SECRET` is set — otherwise accepts unsigned requests and logs a warning | List of SendGrid event objects | `{status: "ok"}` | Email delivery/bounce/unsubscribe receipts, matched to `NotificationDispatch` by `provider_message_id` |
| `POST /sms-delivery` | `X-Jazz-Hmac-Sha256`, only enforced if `JAZZ_SMS_WEBHOOK_SECRET` set | `{message_id or MessageSid, status or SmsStatus}` | `{status: "accepted"}` | SMS delivery receipts (Jazz or Twilio fallback) |
| `POST /whatsapp-delivery` | `X-Whatsapp-Signature`, only enforced if `JAZZ_WHATSAPP_WEBHOOK_SECRET` set | `{message_id, status}` | `{status: "accepted"}` | WhatsApp delivery receipts — `sent`/`delivered`/`read`/`failed` mapped correctly (only `delivered` flips dispatch status to `DELIVERED`; `read` only stamps `read_at` if that column exists) |

Note on the three "conditionally enforced" webhooks: `config.py`'s `_validate_runtime_constraints` refuses to start the service at all outside `ENVIRONMENT=local` unless all four webhook secrets (`AFTERSHIP_WEBHOOK_SECRET`, `SENDGRID_WEBHOOK_SECRET`, `JAZZ_SMS_WEBHOOK_SECRET`, `JAZZ_WHATSAPP_WEBHOOK_SECRET`) are set. So the "fail open" behavior described above is reachable in local dev only, not in a deployed environment — assuming that startup check is never bypassed.

### 2.7 Health & Metrics

| Method & Path | Purpose |
|---|---|
| `GET /health` | Trivial `{"status": "ok", "service": "notification-service"}` — no dependency checks |
| `GET /api/v1/health/live` | Liveness — `{"status": "alive"}`, no dependency checks |
| `GET /api/v1/health/ready` | Readiness — checks Postgres, Redis, event-listener running state, all three queue depths (main/retry/DLQ), and each dispatcher's `health_check()`. Returns 503 if not ready or `degraded` (SMS or push dispatcher down is treated as degraded, others are not) |
| `GET /metrics` | Prometheus metrics (mounted ASGI sub-app, not under `/api/v1`) |

---

## 3. Shipment Status Model

Two different status vocabularies exist and a frontend needs to know which one it's reading.

**`Shipment.status`** (returned by `GET /tracking/{order_id}` and used for the admin issues view) — a free-text string column, populated from AfterShip's `tag` field via this mapping in `tracking_service.py`:

| AfterShip `tag` | `Shipment.status` | Meaning |
|---|---|---|
| `InfoReceived`, `Pending` | `label_created` | Courier has the shipping label, hasn't picked up yet |
| `Pickup` | `picked_up` | Package physically collected |
| `InTransit` | `in_transit` | En route |
| `OutForDelivery` | `out_for_delivery` | On the delivery vehicle, same day |
| `Delivered` | `delivered` | Confirmed delivered — also sets `actual_delivery` |
| `AttemptFail` | `delivery_attempted` | Courier tried and failed to deliver |
| `Exception` | `delivery_exception` | Courier-reported problem |
| `Returned` | `returned` | Sent back to merchant |
| anything unrecognized | `delivery_exception` | Fallback |

`TrackingEvent` rows (the `events` array in the tracking response) are the granular checkpoint history from AfterShip — city, description, timestamp, raw courier payload — deduplicated on `(shipment_id, event_code, event_time)`.

**`Order.status`** — a separate, coarser field on the `Order` row itself (used by Gateway, not returned by this service). Only three of the eight `Shipment.status` values ever cause an `Order.status` transition, and this happens in **two independent places** that must be kept in sync: `TrackingService.process_aftership_webhook` in this service, and Gateway's own `delivery_event_listener` (`apps/gateway/src/services/delivery_events.py`) which reacts to the `delivery.status_changed`/`delivery.confirmed` events this service publishes.

| `Shipment.status` | `Order.status` effect |
|---|---|
| `in_transit` | → `IN_TRANSIT` |
| `delivered` | → `DELIVERED` (also triggers Wakalah execution + installment due-date rescheduling in Gateway) |
| `returned` | → `RETURNED` |
| `label_created`, `picked_up`, `out_for_delivery`, `delivery_attempted`, `delivery_exception` | **No `Order.status` change** — Order stays wherever it was |

**What this means for a tracking UI:** if you build a progress bar purely off `Order.status`, it will jump straight from "in transit" to "delivered" with no visible "out for delivery" or "delivery exception" step — those only ever appear in `Shipment.status` / the `events` array from `GET /tracking/{order_id}`. Build the customer-facing tracking display off that endpoint's `status` + `events`, not off any Order-level field, if you want the granular states to actually render.

---

## 4. Known Gaps & Caveats Relevant to Integration

Each item verified directly against current source on 2026-08-28.

1. **STILL OPEN — No retry path if AfterShip shipment registration fails.** `TrackingService.register_shipment` (`src/services/tracking_service.py:48`) calls `AfterShipClient.create_tracking`, which does `response.raise_for_status()` on any non-2xx AfterShip response with no `try/except`. `POST /tracking/register` has no error handling either. A transient AfterShip outage at the moment an order reaches checkout means that shipment registration fails outright with a 500, no `Shipment` row is created, nothing retries it, and the order has no tracking data until someone notices and re-triggers registration manually. Contrast this with notification dispatch, which has a full DB-backed retry/DLQ pipeline (Section above) — shipment registration has none of that.

2. **STILL OPEN, but narrower than it may sound — courier status detail is not lost, only Order-level status is coarse.** As described in Section 3, `Shipment.status` and `TrackingEvent` preserve all the AfterShip detail (`out_for_delivery`, `delivery_attempted`, `delivery_exception`, `picked_up`, `label_created`). Only `Order.status` collapses these into `in_transit`/`delivered`/`returned`/no-change. If your frontend calls this service's own `GET /tracking/{order_id}` directly, you get the full picture. If it instead relies on Gateway's `GET /orders/{id}/tracking` (which reads `Order.status` plus the same `Shipment` row — see `apps/gateway/src/api/v1/orders.py:121`), the shipment sub-object is still granular, but don't infer delivery-exception/out-for-delivery states from `order_status` alone.

3. **DLQ admin test coverage — could not reproduce the exact "tautological assertion" claim from the prior gaps report.** Grepped the current `tests/test_api/test_admin_notifications.py` and `tests/test_api/test_admin_assertion_auth.py` for `status_code in [...]`-style tautologies and found none — both files assert specific expected status codes (200/403/404). The admin DLQ surface (`/dlq`, `/retry/{id}`, `/dlq/retry-all`, `/dlq/purge`) does have real tests exercising the retry/purge behavior. Treat the older report's claim as stale; re-verify if this matters for your work, since test files change independently of this doc.

4. **FIXED — background workers are wired up.** As of current `main.py`, the notification consumer (drains `NOTIFICATION_QUEUE_KEY`), retry worker (re-enqueues due `RETRYING` dispatches every 5 min by default), reminder worker (fires D-3/D-1 upcoming and D+1/D+7/D+14 overdue installment reminders hourly by default), and scheduled-notification worker (fires due `ScheduledNotification` rows every 60s) all run as in-process asyncio tasks started in the FastAPI lifespan. Previously these existed only as unreferenced `python -m` scripts. If you deploy this service as multiple replicas, be aware all of them run all four workers — there's no leader election, so `BRPOP` on the shared queue naturally load-balances the consumer, but the interval-based sweeps (reminder/retry/scheduled) will all run redundantly on every replica; their idempotency keys make this safe (no duplicate notifications) but it is wasted work at scale.

5. **STILL OPEN — real delivery depends on per-environment provider credentials that default to empty.** All four dispatchers (`JazzSMSDispatcher`, `JazzWhatsAppDispatcher`, `FCMPushDispatcher`, `SendGridEmailDispatcher`) have working HTTP integration code, not mocks — but every credential (`JAZZ_SMS_USERNAME`/`PASSWORD`, `JAZZ_WHATSAPP_API_KEY`, `FCM_SERVICE_ACCOUNT_JSON`, `SENDGRID_API_KEY`, `TWILIO_*`) defaults to an empty string in `config.py`. Without real values configured, SMS/WhatsApp/email dispatch attempts will fail against the real provider (or, for AfterShip specifically, `AfterShipClient.create_tracking` explicitly falls back to a synthetic mock tracking ID when `AFTERSHIP_API_KEY` is empty — that one is a deliberate, documented mock path; the notification dispatchers are not). Don't build a frontend that assumes an SMS/WhatsApp/push/email always arrives — check `GET /api/v1/health/ready`'s `dispatchers` block, or just confirm with whoever owns deploy config which providers are actually live in the target environment.

6. **STILL OPEN — Jazz SMS/WhatsApp/AfterShip webhook signature checks are dev-mode-permissive by code, but blocked by startup validation outside local.** See the note at the end of Section 2.6 — this is a real code path (each handler logs a warning and accepts unsigned webhooks when its secret is unset) but `config.py`'s validator prevents the service from starting at all in a non-local environment unless all four secrets are set. Worth knowing if a future refactor removes or weakens that startup check.

7. **Admin list/stats endpoints don't use their declared response schemas.** `GET /admin/notifications/` returns raw SQLAlchemy `Notification` rows rather than binding to the `AdminNotificationListResponse` Pydantic model defined in `src/schemas/notifications.py` (which includes `user_phone`, `dispatches: [DispatchInfo]`, etc. — none of that shape is actually guaranteed by the endpoint). If you build an admin dashboard against this endpoint, treat the response shape as "whatever FastAPI's default JSON encoding of a SQLAlchemy row produces" and verify field names empirically against a live response rather than trusting the schema file.

8. **`GET /notifications/preferences` doesn't populate `category_label`/`is_mandatory`.** The `NotificationPreferenceItem` schema has these fields but `PreferenceService.get_all_preferences` just returns raw `NotificationPreference` rows, which don't carry them. A preferences UI wanting human-readable category labels or "why can't I turn this off" copy needs to hardcode that mapping client-side (the `NON_OPTOUT_CATEGORIES` set — `auth`, `compliance` — is the source of truth for which categories are non-optional).

---

## 5. Auth & Headers

**This service is not designed to be called directly by an untrusted frontend without a trusted intermediary in front of it.** Two of its three auth mechanisms trust caller-supplied headers with no cryptographic verification of their own:

- **Customer identity (`X-User-Id`)** — `get_current_user_id` in `src/core/dependencies.py` reads the `X-User-Id` header, parses it as an integer, and uses it as-is. There is no JWT decoding, no session lookup, nothing — any caller that can set an HTTP header can claim to be any user ID. This is only safe if the network path guarantees the header is set by something that already verified the caller's identity (e.g., a reverse proxy or gateway that authenticates the customer JWT and injects `X-User-Id` itself) and that nothing else can reach this service directly.
- **Admin identity (`X-Admin-Assertion`)** — this one *is* cryptographically verified: `_verify_admin_assertion` in `dependencies.py` calls `sk_shared.security.verify_signed_assertion`, checking an HMAC signature (keyed on `INTERNAL_API_KEY`, shared with Gateway) and expiry on a short-lived token minted by Gateway (`InternalServiceClient._admin_assertion_headers` in `apps/gateway/src/core/http_client.py`). A caller cannot forge this without the shared secret.
- **Service identity (`X-Internal-Key`)** — constant-time compared against `INTERNAL_API_KEY`. Standard shared-secret internal auth.

**What Gateway currently does, concretely:** Gateway calls this service's `/internal/notifications/otp` endpoint (with `X-Internal-Key`) for every OTP flow, and mints `X-Admin-Assertion` tokens for the two admin routers (`admin_notifications`, `admin_tracking`). **Gateway does not currently proxy the customer-facing endpoints** (`GET /notifications`, `/notifications/preferences`, `GET /tracking/{order_id}`, etc.) — there is no code in `apps/gateway` that calls these routes. Gateway's own `GET /orders/{id}/tracking` endpoint (`apps/gateway/src/api/v1/orders.py:121`) reads the `Shipment`/`TrackingEvent` tables directly from its own DB session rather than calling this service over HTTP — both services share the same Postgres database, so this works, but it means the "customer tracking" and "customer notification inbox" endpoints on *this* service have no existing caller at all in the current backend.

**Practical implication for a new frontend team:** for the customer-facing routes listed in Sections 2.1 and 2.4 (notification inbox, preferences, unsubscribe, single-order tracking), you have two real options — (a) extend Gateway with proxy routes that verify the customer's JWT and forward the call with a correctly-set `X-User-Id` header, mirroring how it already handles OTP/admin calls to this service, or (b) put this service behind whatever edge/gateway layer terminates and verifies customer JWTs in the new architecture, and have that layer inject `X-User-Id`. **Do not expose this service's customer routes directly to the public internet as-is** — `X-User-Id` is trivially spoofable by anyone who can reach the service.

Summary by endpoint group:

| Group | Header | Verified how | Safe to expose directly to internet? |
|---|---|---|---|
| Customer (`/notifications/*`, `/tracking/{order_id}`) | `X-User-Id` | Not verified — trusts the header value | **No** — needs a trusted proxy in front that injects this header post-JWT-verification |
| Internal (`/internal/notifications/*`, `/tracking/register`) | `X-Internal-Key` | Constant-time shared-secret compare | No — internal only |
| Admin (`/admin/notifications/*`, `/admin/tracking/*`) | `X-Admin-Assertion` | HMAC signature + expiry check | No — internal only, minted by Gateway after its own admin auth |
| Webhooks (`/webhooks/*`) | Provider-specific HMAC/ECDSA header | Enforced per-provider (see Section 2.6) | Yes — designed for public provider callbacks, and startup validation blocks unsigned acceptance outside local |
| Health/metrics | none | — | Fine to expose to internal monitoring; `/health` and `/api/v1/health/live` have zero dependency checks so don't rely on them for real readiness |
