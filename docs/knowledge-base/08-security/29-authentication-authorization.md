# Authentication & Authorization

**Status:** STABLE — sourced from `docs/System-md-files/M01-auth.md`.

## Authentication

### Customer

- `POST /auth/register/initiate` — phone (E.164) + name, sends OTP via Jazz SMS, OTP hash stored in Redis (3-min TTL).
- `POST /auth/verify-otp` — max 3 attempts then 5-minute lock; issues JWT (15-min access, 24-hr refresh) and creates a Redis session.
- `POST /auth/login` — OTP-based or password-based.
- `POST /auth/refresh` — Bearer refresh token → new 15-min access token.
- `POST /auth/logout` — revokes the session in Redis and marks `user_sessions.revoked_at`.
- `POST /auth/otp/resend` — rate-limited to 3 resends/hour per phone.

### Admin

- `POST /admin/auth/login` — email + password (bcrypt cost=12) + mandatory TOTP code. No SMS fallback for admin MFA. Session TTL 2 hours (configurable per role).

## JWT details

RS256-signed. Access token: 15-minute expiry. Refresh token: 24-hour expiry, rotated on every use. Session state additionally tracked in Redis (`session:{token_hash}`, `admin:session:{token_hash}`) alongside the DB record, allowing fast revocation checks without a DB round-trip.

**Known gap:** `decode_access_token()` in `sk_shared/security.py` does not distinguish access-token decoding from refresh-token decoding — no separate validation path confirms a token presented as an access token was actually issued as one (`SH-GAP-02`).

## RBAC roles

| Role | Key permissions |
|---|---|
| `super_admin` | All modules, all actions |
| `operations_manager` | Users, Orders, Payments, Support, Reports |
| `credit_risk_analyst` | Risk module, user profiles (financial data only) |
| `fraud_analyst` | Risk/Fraud, Blacklist — read-only elsewhere |
| `cs_agent` | Tickets, user profiles (read-only), order status |
| `finance_analyst` | Financial Ops, Reconciliation — no PII, no order edit |
| `compliance_officer` | Compliance, KYC queue, Audit trails — no account modification |
| `marketing_manager` | Marketing, Analytics (non-PII) — no financial/user data |

**Field-level examples** (from source spec): CS agents can view KYC *status* but cannot view a raw CNIC number. Finance analysts can view all payments but cannot mark one as received.

**Known gap:** the RBAC permission matrix in `rbac.py` is not fully synced with the `@RequirePermission(...)` decorators actually used on admin endpoints — some endpoints reference a permission (e.g. `manage_system`) that isn't assigned to any role in the matrix, meaning that capability is effectively unreachable by any role as coded (`GW-BL-12`).

## Security rules

- Concurrent sessions: 1 per customer — a new login terminates the previous session.
- Inactivity timeout: 2 hours for admin (role-configurable), none enforced for customers.
- IP allowlisting: required for finance and super-admin roles (office IP only).
- Password hashing: bcrypt, cost factor 12.
- MFA secret storage: AES-256 encrypted at rest.

## Internal service authentication

Cross-service calls use a shared `X-Internal-Token`, validated via constant-time comparison — see [`27-security-architecture.md`](27-security-architecture.md).

## Related documents

[`27-security-architecture.md`](27-security-architecture.md), [`28-kyc-verification-workflow.md`](28-kyc-verification-workflow.md), [`../05-architecture/microservices/gateway.md`](../05-architecture/microservices/gateway.md).
