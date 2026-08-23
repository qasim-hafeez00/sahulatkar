# API Testing Strategy

**Status:** STABLE

## Coverage bar

Per [`30-qa-strategy.md`](30-qa-strategy.md): all API endpoints require integration test coverage (pytest + testcontainers, real DB + Redis), and every new endpoint requires at least one happy-path and one error-path test.

## What API testing should specifically verify, given this platform's characteristics

- **Error codes match [`../06-api-events/120-error-standards.md`](../06-api-events/120-error-standards.md)** exactly, not just "returns an error" — since the platform relies on machine-readable `detail` codes for client-side handling.
- **Hard-gate enforcement** on every endpoint that touches VCN issuance, not just the primary path — a hard-gate test should confirm 403 `MURABAHA_NOT_SIGNED` from every conceivable entry point, not just the obvious one.
- **RBAC enforcement per endpoint** — given the confirmed gap where some admin endpoints reference a permission (`manage_system`) not assigned to any role (`GW-BL-12`), API tests should include an explicit "every admin endpoint's required permission is actually assigned to at least one role" check, ideally as an automated test against the RBAC matrix rather than a manual audit.
- **Idempotency behavior** for every state-changing financial endpoint, once the idempotency-key pattern in [`../06-api-events/122-idempotency-standards.md`](../06-api-events/122-idempotency-standards.md) is implemented — testing that a duplicate request returns the original response, not a 500 or a duplicate side effect.

## Internal API surface

Internal (`X-Internal-Token`-authenticated) endpoints need their own test suite verifying the HMAC check actually rejects an invalid/missing token — not just that the happy path with a valid token works, since the internal surface (e.g., the VCN-decrypt endpoint) is exactly where the most severe security gaps in this platform have been found.

## Related documents

[`143-test-strategy.md`](143-test-strategy.md), [`../06-api-events/23-api-standards.md`](../06-api-events/23-api-standards.md), [`../08-security/29-authentication-authorization.md`](../08-security/29-authentication-authorization.md).
