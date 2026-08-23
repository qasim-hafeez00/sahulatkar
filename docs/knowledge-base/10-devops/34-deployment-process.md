# Deployment Process

**Status:** STABLE — sourced from `docs/MASTER_PLAN.md` §9–10 and `.github/workflows/`.

## Git workflow

```
main          ← production-ready, protected, requires PR + 1 approval + CI green
  └── develop ← integration branch, receives feature merges
       └── feature/{service}/{ticket}
       └── fix/{service}/{ticket}
       └── infra/{component}
```

Commit convention: `feat(gateway): ...`, `fix(credit-engine): ...`, `chore(ci): ...`, `docs(specs): ...`, `test(gateway): ...`, `infra(k8s): ...`. PR title format: `[SERVICE] Brief description`; body covers what/why/testing done; requires CI green + 1 approval (self-approve acceptable for a solo contributor per current project stage); squash-merge to `develop`, merge commit to `main`.

## CI pipeline (`.github/workflows/ci.yml`) — every push and PR

```
1. Lint (parallel per service): ruff check + mypy --ignore-missing-imports
2. Unit tests (needs lint): pytest against real Postgres/Redis service containers, --cov-fail-under=80
3. Frontend tests (parallel): npm lint + type-check + vitest --coverage
4. Migration check (needs lint): alembic upgrade head → downgrade -1 → upgrade head (reversibility check)
5. Hard-gate test (needs unit tests): pytest test_hard_gate.py — NEVER skipped
6. Docker build (needs tests): verify every service's Dockerfile builds
```

## CD pipeline (`.github/workflows/build-and-push.yml`) — on merge to `main`

```
1. Detect changed services (build only what changed)
2. Build + push to ECR (tagged with commit SHA and :latest)
3. Deploy to staging (kustomize + kubectl apply, rollout status checked, 300s timeout)
4. Smoke tests on staging (health check + tests/smoke/)
5. Deploy to production — MANUAL APPROVAL GATE (GitHub environment protection), then same rollout pattern
```

## Rollback

**Known gap:** most database migrations lack a working `downgrade()` implementation (`DB-GAP-01`), which means the migration-reversibility check in CI step 4 above is only as meaningful as the migrations that actually have a real downgrade path — a failed production deploy involving a schema change may not be cleanly reversible today. This should be treated as a release-process risk, not just a testing nitpick: **confirm a migration has a working downgrade before shipping a schema change that would need one reverted quickly.**

Application-level rollback (redeploying a prior container image via `kubectl rollout undo` or re-running the CD pipeline against a prior commit SHA) is otherwise standard and not blocked by the migration gap, provided no irreversible schema change shipped alongside it.

## Pre-push checklist (from `docs/MASTER_PLAN.md` §13)

Code quality (ruff/mypy clean, no hardcoded secrets, no `print()`, all endpoints have Pydantic schemas) · Tests (all pass, ≥80% coverage on changed files, hard-gate test passes, new endpoints have happy + error test) · Database (new migration if models changed, migration has a downgrade, all monetary fields `DECIMAL(14,2)`, sensitive fields encrypted) · Docker (builds, <500MB, non-root user) · Documentation (docstrings, README/CHANGELOG updated) · CI/CD (passes locally, no committed secrets, feature-flagged if incomplete).

## Related documents

[`33-infrastructure-architecture.md`](33-infrastructure-architecture.md), [`35-monitoring-logging.md`](35-monitoring-logging.md), [`../09-qa/30-qa-strategy.md`](../09-qa/30-qa-strategy.md).
