# API Standards

**Status:** STABLE (as-practiced conventions, extracted from the actual endpoint patterns across all 6 services) — some items below are observed inconsistencies to standardize, not settled rules.

## Architecture

REST over HTTP, FastAPI (Python 3.12) on every backend service. No GraphQL, no gRPC between services — internal calls are plain REST via `httpx.AsyncClient`.

## Versioning

Endpoints are versioned under `/api/v1` (Gateway customer/admin surface) or `/v1` (other services' internal/external surface) — both patterns appear in the codebase; **not fully standardized** across services. Recommend picking one prefix convention platform-wide.

## Authentication

- **Customer/admin-facing:** JWT bearer token, RS256-signed, in the `Authorization: Bearer <token>` header. Access tokens: 15-minute expiry. Refresh tokens: 24-hour expiry, rotated on each use.
- **Admin:** same JWT mechanism, plus mandatory TOTP MFA at login (no SMS fallback).
- **Internal (service-to-service):** shared `X-Internal-Token` HMAC, validated via constant-time comparison (`secrets.compare_digest` / `hmac.compare_digest` — both used, consistently, per the audit's duplication analysis).
- **Webhooks:** HMAC-SHA256 signature validation against a provider-specific shared secret (e.g. `X-Aftership-Hmac-Sha256`). **Known gap:** the SendGrid webhook currently has no signature verification at all (`NS-BL-01`) — this should be treated as a standards violation to fix, not a one-off.

Full detail: [`../08-security/29-authentication-authorization.md`](../08-security/29-authentication-authorization.md).

## Error standards

Errors follow FastAPI's standard `HTTPException` shape with a `detail` field carrying a machine-readable code, e.g.:

```json
{ "detail": "MURABAHA_NOT_SIGNED" }
```

Observed error codes across services include `PHONE_ALREADY_REGISTERED` (409), `INVALID_PHONE_FORMAT` (422), `INVALID_OTP` / `OTP_EXPIRED` (400), `TOO_MANY_ATTEMPTS` (429), `CNIC_BLOCKED` / `CNIC_EXPIRED` / `OCR_FAILED` (422), `NADRA_UNAVAILABLE` (503), `NOT_A_PRODUCT_URL` / `PROHIBITED_CATEGORY` / `OUT_OF_STOCK` (422), `MURABAHA_NOT_SIGNED` (403), `CONFIRMATION_REQUIRED` / `ALREADY_SIGNED` (400/409). This SCREAMING_SNAKE_CASE convention is consistent and should be maintained for any new error code.

**Known gap:** some endpoints return generic 500s where a specific status/code would be correct — e.g. Ledger Service's `GET /api/entries/{entry_number}` catches `LookupError` but returns 500 instead of 404 (`LS-EP-04`).

## Pagination

Two competing implementations exist today: Gateway's manual pagination and Product Service's own `_encode_cursor()`/`_decode_cursor()`. `sk_shared/pagination.py` already provides a shared `PaginationParams` helper — the standard should be **cursor-based pagination via `sk_shared/pagination.py`**, and the duplicated implementations should be migrated to it (tracked in [`../05-architecture/21-service-responsibility-matrix.md`](../05-architecture/21-service-responsibility-matrix.md)).

## Idempotency

For financial transactions (payments, VCN issuance), idempotency keys are used (e.g. `PaymentWorkflow.idempotency_key`) — but currently enforced only via a database uniqueness constraint, with no application-layer pre-check. This means a concurrent duplicate request surfaces as a raw DB constraint violation (500) instead of a clean idempotent 200 response (`PO-BL-06`). **Standard to adopt:** every state-changing financial endpoint must accept a client-supplied idempotency key, check for it in the application layer before attempting a write, and return the original response on a repeat.

## Webhook standards

HMAC-SHA256 signature verification is the platform standard (see Authentication above) — every webhook receiver should follow the AfterShip/JazzCash/Safepay pattern, not the SendGrid exception. Webhook handlers should also deduplicate by provider transaction ID before acting — currently **not** done consistently (JazzCash/Safepay webhooks validate HMAC and enqueue but don't dedupe, `GW-BL-13`).

## External integration documentation

Per-provider integration detail (NADRA, TASDEEQ, Shufti Pro, Stripe Issuing, Safepay, JazzCash, EasyPaisa, AfterShip, Rye API) is not yet consolidated into standalone documents in this knowledge base pass — each is referenced inline within the relevant workflow/microservice document instead (see [`../05-architecture/22-microservice-documentation.md`](../05-architecture/22-microservice-documentation.md)). Recommend adding dedicated per-provider integration guides as a follow-up pass once each integration is confirmed live (several, like NADRA/Shufti Pro, are currently stubs per the audit).

## Related documents

[`24-event-catalog.md`](24-event-catalog.md), [`../08-security/29-authentication-authorization.md`](../08-security/29-authentication-authorization.md).
