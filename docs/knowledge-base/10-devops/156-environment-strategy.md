# Environment Strategy

**Status:** STABLE — expanded from [`33-infrastructure-architecture.md`](33-infrastructure-architecture.md)'s environment table.

## Environments

| Env | Purpose | Database | Deployment trigger |
|---|---|---|---|
| local | Individual development | docker-compose PostgreSQL | Manual (`docker-compose up`) |
| test | CI automated tests | testcontainers PostgreSQL (ephemeral, per-run) | Every push/PR |
| staging | Pre-production validation | RDS staging (smaller instance, single AZ) | Every merge to `main` (automatic) |
| production | Live | RDS production (multi-AZ, r6g.xlarge) | Manual approval gate after staging smoke tests pass |

## Parity considerations

Staging uses smaller instances and single-AZ (per [`33-infrastructure-architecture.md`](33-infrastructure-architecture.md)) — this is a reasonable cost optimization but means staging cannot fully validate production-scale behavior (e.g., the billing sweep's "100K rows in <60s" performance claim, or multi-AZ failover behavior) — [`../09-qa/153-performance-testing.md`](../09-qa/153-performance-testing.md)'s load testing should account for this gap by either testing directly against a production-sized environment or explicitly documenting which behaviors staging cannot validate.

## Configuration management per environment

`.env` locally, GitHub Actions secrets in CI, AWS Secrets Manager → ExternalSecrets in staging/production — see [`../08-security/138-secrets-management.md`](../08-security/138-secrets-management.md) for the full detail (not duplicated here).

## What's not documented

No explicit environment-promotion policy beyond "staging auto-deploys, production requires manual approval" — e.g., is there a minimum bake time in staging before production promotion is allowed? Is there a defined smoke-test suite staging must pass before the production approval gate even becomes available (partially yes — `tests/smoke/` exists per [`34-deployment-process.md`](34-deployment-process.md))? Recommend this be made explicit as the platform matures past its current solo/small-team development stage.

## Related documents

[`33-infrastructure-architecture.md`](33-infrastructure-architecture.md), [`34-deployment-process.md`](34-deployment-process.md), [`157-cicd-documentation.md`](157-cicd-documentation.md).
