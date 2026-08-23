# Gateway Service

**Status:** STABLE (design) — 85% complete per `docs/PRODUCTION_GAPS_REPORT.md` estimate.

## Purpose

The single entry point (Backend-for-Frontend) for both `web-customer` and `web-admin`. Owns authentication, KYC orchestration, RBAC, hard-gate enforcement, contract generation/signing, and routing to downstream services.

## Responsibilities

- Auth: phone OTP registration/login, JWT issuance (RS256, 15-min access / 24-hr refresh), admin login with mandatory TOTP MFA.
- KYC orchestration: CNIC upload (S3 presigned), NADRA/Shufti Pro calls, manual review queue.
- Shariah contracts: Wakalah + Murabaha generation and OTP signing.
- Hard gate: blocks VCN issuance until `order.status == 'contracts_signed'`.
- RBAC: 8 defined roles, permission-decorator enforcement on admin endpoints.
- Admin surface: user management, order management, KYC decisions, compliance/audit views, analytics.

## Dependencies

Redis (sessions, OTP, rate limits), PostgreSQL (users, KYC, contracts, orders), Product Service (internal callbacks for extraction results), Credit Engine (credit checks), Payment Orchestrator (payment/VCN callbacks), NADRA Verisys, Shufti Pro.

## Endpoint surface (implemented, per audit)

84+ endpoints: 29 customer-facing, 45+ admin, 8 internal, 2 webhooks. Full list of implemented vs. missing endpoints: `docs/PRODUCTION_GAPS_REPORT.md` §2.

## Key APIs

See [`../../08-security/29-authentication-authorization.md`](../../08-security/29-authentication-authorization.md) for auth APIs, [`../../08-security/28-kyc-verification-workflow.md`](../../08-security/28-kyc-verification-workflow.md) for KYC, and `docs/System-md-files/M05-contracts.md` for contract APIs.

## Events

Consumes internal callbacks from Product Service, Credit Engine, Payment Orchestrator, Notification Service. **Should publish** `loan.created` on Murabaha signing — currently does not (highest-severity cross-service gap, see [`../../02-business-workflows/07-bnpl-workflow-e2e.md`](../../02-business-workflows/07-bnpl-workflow-e2e.md)).

## Database ownership

`users`, `admin_users`, `user_sessions`, `user_kyc_verifications`, `user_devices`, `kyc_verification_queue`, `wakalah_agreements`, `murabaha_contracts`, `contract_digital_signatures`, `orders`, `audit_trails`.

## Known gaps (highest severity first, from `docs/PRODUCTION_GAPS_REPORT.md` §2)

- **GW-BL-01 (critical):** no credit reservation at order initiation — `available_credit` not decremented, allowing double-spend across concurrent orders.
- **GW-BL-03/04 (high):** Murabaha can be generated without Wakalah being signed first; no cancellation path exists once contracts are signed but before a VCN is issued.
- **GW-BL-05 (high):** admin TOTP has no brute-force lockout after failed attempts.
- **GW-BL-06 (high):** payment confirmation and order-status update are separate, uncompensated transactions.
- **GW-GAP-01/02 (high):** system parameters (min down payment %, max credit limit, late fee rate) have no CRUD API — effectively hardcoded.
- Full checklist: `docs/PRODUCTION_GAPS_REPORT.md` §2, §13.

## Security

See [`../../08-security/27-security-architecture.md`](../../08-security/27-security-architecture.md).
