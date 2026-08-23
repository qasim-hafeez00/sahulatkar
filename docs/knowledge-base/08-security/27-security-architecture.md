# Security Architecture

**Status:** STABLE (design) — known gaps flagged inline from the 2026-04-27 audit.

## Layered defense model

1. **Edge:** NGINX Ingress — SSL/TLS termination, rate limiting.
2. **Identity:** RS256 JWT, singleton session tracking in Redis.
3. **Hard gates:** workflow-level enforcement independent of role/permission checks (e.g., VCN issuance blocked without `contracts_signed`, regardless of who's asking).
4. **Internal auth:** every cross-service call requires a shared, KMS-stored `X-Internal-Token` HMAC.
5. **Data security:** PII encrypted at rest via `pgcrypto` AES-256.

## Authentication & session management

See [`29-authentication-authorization.md`](29-authentication-authorization.md) for full detail. Summary: 15-min JWT access tokens, 24-hr refresh tokens (rotated on use), mandatory TOTP MFA for all admin accounts (no SMS fallback), one concurrent session per customer (new login terminates the old one), 2-hour admin inactivity timeout (configurable per role), IP allowlisting for finance and super-admin roles.

## Encryption

- **At rest:** `pgcrypto` AES-256 for CNIC, IBANs, VCN PAN/CVV/expiry, and admin MFA secrets — column-level, not just disk-level.
- **In transit:** TLS at the ingress; internal service calls are expected to run within the cluster's private network.
- **VCN handling rule (immutable):** PAN/CVV are never logged in application logs, anywhere, under any circumstance — only masked card numbers (`**** **** **** 1234`) appear in logs or API responses.

## Secrets management

Local development: `.env` file (gitignored). CI: GitHub Actions secrets. Staging/production: AWS Secrets Manager → Kubernetes ExternalSecrets. See `docs/SECRETS_MANAGER_MIGRATION.md` for the migration detail (kept in place, operational document rather than duplicated here). **Known gap:** no secret-rotation mechanism exists — a single compromised secret (JWT private key, Stripe key, gateway credentials) currently requires a full code/config deploy to rotate (`INF-GAP-07`). No secret-scanning (e.g. Gitleaks) is wired into CI either (`INF-GAP-09`).

## Threat model highlights (from the code audit, not a formal STRIDE exercise)

| Threat | Current exposure | Mitigation status |
|---|---|---|
| VCN credential exfiltration | Internal VCN-decrypt endpoint (used by the checkout agent) has **no rate limiting** — a compromised Product Service instance or leaked internal token could mass-retrieve plaintext PAN/CVV for all active orders | **Open (PO-BL-01)** |
| Admin TOTP brute force | No lockout after repeated failed TOTP attempts is currently implemented, despite being referenced as a requirement (TASK-16) | **Open (GW-BL-05)** |
| Refresh-token misuse | `decode_access_token()` uses the same decoding path for access and refresh tokens with no distinct validation — a refresh token could potentially be used where an access token is expected | **Open (SH-GAP-02)** |
| Webhook forgery | AfterShip/JazzCash/Safepay webhooks are HMAC-verified; **SendGrid's is not** — anyone can currently POST to that endpoint and trigger unsubscribe/preference changes | **Open (NS-BL-01)** |
| Audit-trail tampering/deletion | `audit_trails` is a normal, deletable table rather than an append-only/immutable store | **Open (INF-GAP-08)** |
| Cross-service internal-call forgery | Mitigated by shared HMAC token, consistently implemented across services per the audit's duplication analysis | Adequately mitigated |
| SQL injection | Parameterized queries via SQLAlchemy throughout | Adequately mitigated by framework choice |
| XSS | Next.js default escaping + intended CSP headers | Design-adequate; not independently penetration-tested per current docs |

## Fraud & account-takeover prevention

Handled primarily by the Credit Engine's Layer 1 (hard blocks: blacklist, emulator detection, new-account VPN) and Layer 2 (velocity rules: order/KYC/promo abuse windows) — see [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md). Device fingerprinting (FingerprintJS Pro) feeds both KYC and credit scoring.

## Data residency

All data is committed to stay within AWS `ap-south-1`, cited as a PECA 2016 compliance requirement — see [`../11-compliance/36-compliance-requirements-matrix.md`](../11-compliance/36-compliance-requirements-matrix.md) for the compliance basis (flagged there as pending legal confirmation).

## Security incident response

See [`../12-operations/41-incident-response-plan.md`](../12-operations/41-incident-response-plan.md).

## Security checklist (from `docs/MASTER_PLAN.md`, as design intent — not all items independently verified as implemented)

All PII encrypted at rest · all endpoints authenticated except `/health`, `/auth/register`, `/auth/verify-otp` · rate limiting on public endpoints · HMAC-SHA256 on webhooks · CORS restricted to known origins · parameterized queries · CSP headers · CSRF tokens on state-changing frontend requests · no secrets in code/logs/error responses · VCN PAN/CVV never logged · admin MFA required · audit trail on sensitive operations · data residency `ap-south-1` only · PECA 2016 OTP-based e-signatures.

## Related documents

[`28-kyc-verification-workflow.md`](28-kyc-verification-workflow.md), [`29-authentication-authorization.md`](29-authentication-authorization.md), [`../11-compliance/36-compliance-requirements-matrix.md`](../11-compliance/36-compliance-requirements-matrix.md).
