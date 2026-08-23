# API Architecture

**Status:** STABLE — the structural view complementing [`23-api-standards.md`](23-api-standards.md)'s convention-level detail.

## Pattern

REST-over-HTTP, BFF (Backend-for-Frontend) topology: `web-customer` and `web-admin` both talk exclusively to Gateway, never directly to the other 5 services. Gateway then fans out via internal REST calls (`X-Internal-Token` authenticated) to Product Service, Credit Engine, Payment Orchestrator, Ledger Service, and Notification Service.

## Why BFF rather than direct-to-microservice frontend calls

Centralizes auth, RBAC, and — critically — hard-gate enforcement (VCN issuance blocked without `contracts_signed`) at a single choke point, rather than requiring every service independently re-implement the same gate correctly. This is a deliberate architectural choice with a real payoff: a hard-gate bug only needs to be found and fixed in one place.

## Internal API surface vs. external API surface

Each service exposes both a public-ish surface (reachable, with appropriate auth, from Gateway on behalf of a customer/admin) and an internal-only surface (callbacks, VCN decrypt, etc.) — distinguished by convention (`/internal/` path prefixes) and by requiring the internal HMAC token rather than a user JWT. See [`../08-security/27-security-architecture.md`](../08-security/27-security-architecture.md).

## No API gateway/service mesh layer documented

There's no Kong/Envoy/Istio or similar API-gateway product referenced in engineering docs — routing, auth, and rate limiting are implemented directly in each FastAPI service's own middleware, with Gateway itself acting as the closest thing to an API gateway. This is a reasonable choice at current scale; worth revisiting if internal-call volume or cross-cutting concerns (circuit breaking, retries) grow complex enough to warrant a dedicated layer.

## Related documents

[`23-api-standards.md`](23-api-standards.md), [`../05-architecture/20-system-architecture.md`](../05-architecture/20-system-architecture.md), [`../05-architecture/21-service-responsibility-matrix.md`](../05-architecture/21-service-responsibility-matrix.md).
