# CI/CD Documentation

**Status:** STABLE — the reference-format companion to [`34-deployment-process.md`](34-deployment-process.md), which covers the same ground narratively; this document is structured as a quick-lookup pipeline reference.

## CI pipeline (`.github/workflows/ci.yml`)

| Stage | Runs on | Gate |
|---|---|---|
| Lint | Every push/PR | `ruff check` + `mypy`, zero violations |
| Unit test | After lint | pytest, matrix across all 6 services, real Postgres/Redis containers, `--cov-fail-under=80` |
| Frontend test | Parallel | lint + type-check + vitest --coverage |
| Migration check | After lint | `alembic upgrade head → downgrade -1 → upgrade head` |
| Hard-gate test | After unit test | `test_hard_gate.py` — never skipped |
| Docker build | After test + frontend | Verify every Dockerfile builds |

## CD pipeline (`.github/workflows/build-and-push.yml`)

| Stage | Trigger |
|---|---|
| Detect changed services | Merge to `main` |
| Build + push to ECR | Only changed services, tagged by commit SHA + `:latest` |
| Deploy to staging | Automatic |
| Smoke test on staging | Automatic (`tests/smoke/`) |
| Deploy to production | **Manual approval gate** (GitHub environment protection) |

## Pipeline gaps worth flagging from a CI/CD-specifically lens

- No secret scanning stage (`INF-GAP-09`) — should be added as an early CI stage, before lint, so a leaked credential is caught before any further pipeline work happens.
- No `alembic upgrade head` step in the Kubernetes deployment manifest itself (`INF-GAP-11`) — meaning even though CI verifies migrations are *runnable*, production deploy doesn't currently *run* them automatically; this is a manual step today, a real gap between "CI validated it" and "it's actually applied."
- Migration reversibility check exists but most migrations lack a working `downgrade()` (`DB-GAP-01`) — worth confirming exactly what the CI check is actually verifying, since it presumably isn't catching this gap.

## Related documents

[`34-deployment-process.md`](34-deployment-process.md), [`158-rollback-process.md`](158-rollback-process.md), [`../07-database/134-migration-standards.md`](../07-database/134-migration-standards.md).
