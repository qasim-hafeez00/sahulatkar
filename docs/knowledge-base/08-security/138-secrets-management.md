# Secrets Management

**Status:** STABLE — expanded from [`27-security-architecture.md`](27-security-architecture.md), with the rotation gap given its own focused treatment.

## Per-environment secret storage

| Environment | Mechanism |
|---|---|
| Local | `.env` file (gitignored) |
| CI | GitHub Actions secrets |
| Staging/Production | AWS Secrets Manager → Kubernetes ExternalSecrets |

See `docs/SECRETS_MANAGER_MIGRATION.md` for the migration detail — an operational runbook document kept in place rather than duplicated here.

## Secrets inventory (from `docs/MASTER_PLAN.md`'s `.env` template)

JWT signing keys (RS256 private/public), `PG_PASSWORD`, `REDIS_PASSWORD`, NADRA API key, Shufti Pro client ID/secret, Stripe secret key, Safepay API key, JazzCash merchant ID/password, AfterShip API key, OpenAI API key, BrightData proxy URL, plus AWS-specific values (S3 bucket names, ECR registry).

## Rotation — the confirmed gap

**No secret-rotation mechanism exists** (`INF-GAP-07`). A single compromised secret currently requires a full code/config deploy to rotate, rather than a quick, isolated rotation. Given the inventory above includes payment-gateway credentials and the JWT signing key (whose compromise would let an attacker forge valid session tokens for any user), this is a meaningful exposure window if any one of these leaks.

## Secret scanning — the second confirmed gap

**No secret-scanning tool (e.g., Gitleaks) is wired into CI** (`INF-GAP-09`) — a credential accidentally committed to the repository would not be automatically detected.

## Recommended priority order for closing these two gaps

1. Secret scanning first (cheap to add, catches the easiest class of leak — an accidental commit — before it ever reaches a deployed environment).
2. Rotation mechanism second (more infrastructure work, but closes the "what do we do if a secret *does* leak" gap that scanning alone doesn't solve for secrets that were never committed to git but leaked another way — e.g., a compromised CI runner).

## Related documents

[`27-security-architecture.md`](27-security-architecture.md), `docs/SECRETS_MANAGER_MIGRATION.md`, [`../10-devops/33-infrastructure-architecture.md`](../10-devops/33-infrastructure-architecture.md).
