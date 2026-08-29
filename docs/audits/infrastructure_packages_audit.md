# Infrastructure & Shared Packages Reference

**Audience**: a new team member (and their AI coding agent) building fresh
frontends against the existing SahulatKar backend. The old frontends
(`apps/web-customer`, `apps/web-admin`) are being discarded; this backend,
its shared Python package, and its local dev stack are not.

**Scope of this doc**: how to run the whole backend locally, what
`packages/shared-python` provides as the source of truth for data shapes,
how many DB migrations exist and what to watch out for, what CI actually
checks, and an honest read of the Terraform/K8s code. Section 2 (Running the
Full Stack Locally) is what you need on day one — everything past it is
background you can skim once.

Every claim below was checked against the actual files in this repo as of
2026-08-28. Where something couldn't be verified from the repo alone (e.g.
whether Terraform has ever actually been applied against a real AWS
account), that's stated explicitly rather than guessed.

---

## 1. Purpose

You're building a new frontend against a backend that already exists,
already runs, and already has real bugs that were found and fixed by
actually running it (see `docs/PRODUCTION_GAPS_REPORT_2026-08.md`). The
fastest path to a working integration is: bring the real backend up locally
with Docker Compose, point your frontend at `http://localhost:8000` (the
gateway), and treat `packages/shared-python/sk_shared/models/` as the
ground truth for what a JSON payload will actually look like — not any
frontend-side type file, which may be stale or was written against the
services before recent fixes.

You do **not** need to understand Terraform or Kubernetes to build a
frontend. Section 6 is included only so you know what's there and what
isn't; skip it unless you're asked to touch deployment.

---

## 2. Running the Full Stack Locally

### The real service list (`infra/docker/docker-compose.yml`)

| Service | Container | Host port | Notes |
|---|---|---|---|
| postgres | `sk-postgres` | 5434 → 5432 | `timescale/timescaledb:2.14.2-pg16`, db `sahulatkar`, user `sk_admin` |
| pgbouncer | `sk-pgbouncer` | 6432 | transaction pooling; all app services connect through this, not directly to postgres |
| redis | `sk-redis` | 6379 | `redis:7.2-alpine`, password-protected, AOF persistence on |
| gateway | `sk-gateway` | 8000 | public API entrypoint; Redis logical DB 0 |
| product-service | `sk-product-service` | 8001 | extraction + checkout automation; Redis DB 1 |
| product-service-scraping-worker | `sk-product-service-scraping-worker` | — | background worker, no port |
| product-service-checkout-worker | `sk-product-service-checkout-worker` | — | background worker, no port |
| product-service-vcn-verifier | `sk-product-service-vcn-verifier` | — | background worker, no port |
| product-service-price-staleness-worker | `sk-product-service-price-staleness-worker` | — | background worker, no port |
| product-service-dlq-monitor | `sk-product-service-dlq-monitor` | — | background worker, no port |
| product-service-execution-reaper | `sk-product-service-execution-reaper` | — | background worker, no port |
| credit-engine | `sk-credit-engine` | 8002 | Redis DB 2 |
| payment-orchestrator | `sk-payment-orchestrator` | 8003 | Redis DB 3 |
| ledger-service | `sk-ledger-service` | 8004 | Redis DB 4 |
| notification-service | `sk-notification-service` | 8005 | Redis DB 5 |
| web-customer | `sk-web-customer` | 3000 | old Next.js app — being discarded, kept here only as a live example of the API contract until replaced |
| web-admin | `sk-web-admin` | 3001 | same caveat as web-customer |
| pgadmin | `sk-pgadmin` | 5050 | `admin@sahulatkar.com` / `admin` |

The six `product-service-*-worker` services matter even if you never touch
product-service directly: without them, nothing consumes the scraping queue
or runs checkout automation, so orders get stuck at `processing` forever.
They're real services in the compose file, not optional extras.

### Bringing it up

```bash
docker compose -f infra/docker/docker-compose.yml up -d
```

or, from the repo root, `make up` (thin wrapper around the same command —
see `Makefile`). On Windows without Docker, `start_all.ps1` runs the six
Python services directly via `uvicorn` against a locally-installed Postgres
(port 5432)/Redis instead of containers — check it before assuming ports
match the Docker setup (it uses 5432, not the Compose stack's 5434).

Run migrations before or after bringing services up:

```bash
docker compose -f infra/docker/docker-compose.yml run --rm gateway \
  alembic -c /app/db/alembic.ini upgrade head
```

An `.env` file at the repo root is required (`env_file: ../../.env` in the
compose file). Copy `.env.example` and fill in what you need — most payment/
KYC/scraping provider keys can stay blank; the services fall back to mock/
local-disk behavior when unset (see the comments in `.env.example` itself,
e.g. `NADRA_PROVIDER=mock`, S3 falls back to local disk if `S3_BUCKET` is
unset).

### Known gotchas (verified against `tests/e2e/README.md` and the compose files)

- **Compose project name.** `docker-compose.yml` has no `name:` key and
  nothing pins `COMPOSE_PROJECT_NAME`. The six worker services above all
  reference `image: docker-product-service` directly (they intentionally
  reuse product-service's build rather than building their own image).
  That image tag only resolves for free when the Compose *project name* is
  exactly `docker` — which is NOT automatic when you run
  `docker compose -f infra/docker/docker-compose.yml ...` from the repo
  root (the default project name there is derived from the current
  directory, e.g. `sahulatkar`, not the compose file's own directory). If
  you see the worker containers fail to start with an image-not-found
  error, pin the project name explicitly:
  ```bash
  docker compose -p docker -f infra/docker/docker-compose.yml up -d
  ```
  or `cd infra/docker` first and drop `-f`. This is a real, previously
  hit issue, not theoretical — see the long comments in
  `docker-compose.yml` above `product-service-scraping-worker` and in
  `docker-compose.e2e.yml`.
- **Don't use `up -d --build` on the base compose file.** The worker
  services inherit an anonymous `build: {context: ../../}` from the
  `x-python-service` YAML anchor with no `dockerfile:`. `--build` tries to
  build them directly and fails (`open Dockerfile: no such file or
  directory`). Build the six services that have real Dockerfiles first,
  then `up -d` without `--build` — this is exactly what `make up` and the
  E2E test fixture (`tests/e2e/conftest.py`) do.
- **PgBouncer + asyncpg prepared statements.** PgBouncer runs in
  `PGBOUNCER_POOL_MODE=transaction`, under which a single logical
  connection can be handed different backend connections between
  statements — asyncpg's client-side prepared-statement cache doesn't
  tolerate that. Every service must create its SQLAlchemy engine with
  `connect_args={"statement_cache_size": 0}`. The shared engine in
  `packages/shared-python/sk_shared/database.py` already does this; it was
  a real, live-verified bug that `apps/ledger-service/src/core/database.py`
  (which builds its own separate engine instead of importing the shared
  one) was missing this and silently dropped real financial events to the
  DLQ. If you ever add a new service or a script that talks to Postgres
  directly through PgBouncer, carry this forward.
- **Internal service token mismatch.** Every service reads
  `INTERNAL_SERVICE_TOKEN` (payment-orchestrator calls it
  `INTERNAL_API_TOKEN`) for service-to-service auth, and each defaults to a
  *different* placeholder if unset — so cross-service calls 401 silently
  unless you set the same value for all of them. The compose file already
  pins all of them to `local-internal-token`; don't touch that if you add a
  new consumer of these APIs.
- **Frontend cookies over plain HTTP.** If you build a new Next.js (or
  similar SSR) frontend against this stack in Docker, set
  `COOKIE_INSECURE=true` the way `web-customer`/`web-admin` do — there's no
  TLS termination in local Compose, so a `Secure` cookie issued by a
  production-mode Next.js build is silently dropped by the browser and
  login looks like it fails with no error.
- **`NEXT_PUBLIC_*` env vars here are still server-only.** Despite the
  prefix, every real call site in the old frontends is server-side
  (Next.js API routes proxying to the gateway), so these must be set to the
  Docker-internal service name (`http://gateway:8000/api/v1`), not
  `localhost`. Worth knowing even though these specific apps are being
  discarded — the same pattern will apply to whatever replaces them if it's
  also an SSR framework talking to the gateway from inside the same Docker
  network.

### E2E overlay (`infra/docker/docker-compose.e2e.yml`)

A second compose file, meant to be layered on top of the base one, adds a
mock-merchant fixture and a few SSRF-allowlist/proxy overrides so
`tests/e2e/test_order_lifecycle.py` can run a full real order lifecycle
(register → KYC → extract → offer → contracts → pay → VCN → checkout
automation → ledger posting) against real containers, no service mocked.
Not something a frontend engineer needs to run day to day, but it's the
only cross-service/E2E test that exists in the repo today, and reading
`tests/e2e/README.md`'s "Real bugs found and fixed" section is a fast way
to understand real integration failure modes (event Redis-DB-boundary
crossing, missing tables, ORM/migration drift) that a frontend calling
these same APIs could otherwise surface again.

```bash
docker compose -f infra/docker/docker-compose.yml \
                -f infra/docker/docker-compose.e2e.yml \
                up -d --build
pytest tests/e2e/ -v
```

---

## 3. `sk_shared` (shared-python package)

`packages/shared-python/sk_shared/` is imported by all six backend Python
services (`gateway`, `product-service`, `credit-engine`,
`payment-orchestrator`, `ledger-service`, `notification-service`). A
frontend engineer won't import this directly, but it's the definitive
answer to "what does this API actually return" — more reliable than
reverse-engineering a route handler, and more reliable than the old
frontends' own TypeScript types, which can drift.

Actual top-level modules (verified by listing the directory — this is not
the old doc's list):

- `models/` — canonical SQLAlchemy models, split into 16 files by domain:
  `auth.py`, `kyc.py`, `product.py`, `order.py`, `cart.py`, `contracts.py`,
  `payment.py`, `ledger.py`, `checkout.py`, `hitl.py`, `delivery.py`,
  `audit.py`, `admin.py`, `notification.py`, `webhook.py`, `credit.py`,
  plus `base.py` for shared mixins (`TimestampMixin`, `UUIDMixin`,
  `SoftDeleteMixin`). `models/__init__.py` re-exports ~66 model classes.
- `security.py` — JWT (RS256, via `python-jose`) access/refresh token
  creation and decoding with a `token_type` claim (`access` / `refresh` /
  `admin` / `temp`), Fernet-based PII encryption, and password hashing
  (`pbkdf2_sha256` by default, `bcrypt` accepted for verification).
- `redis_client.py` — an async wrapper (`RedisClient`) around
  `redis.asyncio`: basic get/set/incr, `set_nx` for atomic claim locks, and
  a full Redis Streams API (`xadd`/`xgroup_create`/`xreadgroup`/`xack`/
  `xautoclaim`) for at-least-once delivery, separate from the fire-and-
  forget pub/sub path.
- `events.py` — the canonical list of event names (`EVENT_*` constants,
  e.g. `payment.down_payment_confirmed`, `ledger.journal_posted`,
  `credit.approved`), a Pydantic `EventEnvelopeSchema` that rejects any
  event name not in the registered set, and `event_channel(name)` which
  namespaces every channel as `sk:events:{event_name}`. Each service
  connects to its own Redis **logical database** (gateway=0,
  product-service=1, credit-engine=2, payment-orchestrator=3,
  ledger-service=4, notification-service=5, matching the compose file) —
  pub/sub messages cross that boundary, plain keys do not. This exact
  distinction caused a real bug (a VCN-charge confirmation key written on
  db=3 was invisible to a poller on db=1); see `tests/e2e/README.md` for
  the full account.
- `database.py` — the shared async SQLAlchemy engine/session factory,
  already configured with `connect_args={"statement_cache_size": 0}` for
  PgBouncer compatibility (see the gotcha above).
- `middleware.py`, `correlation.py` — request-ID / correlation-ID
  propagation and logging middleware.
- `pii.py`, `secrets_manager.py`, `storage.py` — PII helpers, an AWS
  Secrets Manager settings-override loader, and an S3 client (falls back to
  local disk if `S3_BUCKET` is unset).
- `boot_validation.py`, `constants.py`, `credit_reason_codes.py`,
  `exceptions.py`, `notifications.py`, `pagination.py`, `rate_limit.py` —
  smaller shared utilities (startup config validation, shared exception
  types, standard pagination response shape, rate-limit helpers, credit
  decision reason codes).

**Known risk pattern worth flagging to whoever next touches this package:**
this cycle surfaced multiple cases of the SQLAlchemy models in `models/`
drifting out of sync with what Alembic had actually applied to the real
database — e.g. `Order.product_snapshot` existed in Postgres since
migration 016 but was never declared on the ORM model, and six models in
`models/ledger.py` (`JournalEntry`, `LedgerAccount`, `LedgerPeriod`,
`LateFeeCharityAllocation`, `JournalEntryLine`, `LedgerAccountBalance`)
were each missing real columns, only caught by actually running the ledger
flow against real Postgres and fixed via migrations 089–091. If you (or
your agent) add a new field to any model here, double-check there's a
matching, applied migration — SQLite (used in this repo's unit tests)
tolerates a schema mismatch that real Postgres won't.

---

## 4. Database Migrations

`db/migrations/versions/` is Alembic-managed. **93 migration files** exist
as of 2026-08-28 (verified by directory listing, not the old doc's claim of
42). Numbering runs 001 through 091, with two irregularities worth knowing
about if you're grepping by number: `041` has two files
(`041_production_hardening.py` and `041_production_hardening.sql` — the
`.sql` is not a separate migration, just a companion file) and one file is
suffixed `049a_add_system_parameters_and_risk_blacklist.py`. The most
recent migrations:

- `091_ledger_orm_drift_sweep_2.py`
- `090_ledger_orm_drift_sweep.py`
- `089_add_journal_entries_source_reference.py`
- `088_add_prohibited_merchant_domains_table.py`
- `087_shariah_approvals_and_webhook_dedup.py`
- `086_drop_misleading_installments_index.py`
- `085_journal_entry_lines_balance_trigger.py`

Migrations 088–091 are the direct fix for the ORM/migration-drift pattern
described in Section 3 — 089–091 specifically close out a full diff of
`sk_shared/models/ledger.py` against the real, fully-migrated schema, and
088 creates a `prohibited_merchant_domains` table that a live code path
(`ProhibitedCheckerService.check_url`) had been silently querying against
nothing (masked by a bare `except Exception: pass` and SQLite's tolerance
for the failing statement — real Postgres 500'd every call).

Apply migrations against a running stack with:

```bash
docker compose -f infra/docker/docker-compose.yml run --rm gateway \
  alembic -c /app/db/alembic.ini upgrade head
```

CI's `migration-check` job (see below) verifies `upgrade head` →
`downgrade -1` → `upgrade head` all succeed against a clean Postgres on
every push, so a broken migration chain shouldn't reach `main` — but that
only checks the chain runs cleanly, not that every ORM model matches what
it produces (see Section 3's risk pattern).

---

## 5. CI/CD

Two real GitHub Actions workflows exist: `.github/workflows/ci.yml` and
`.github/workflows/build-and-push.yml`. Both were read in full for this
doc — this is what they actually do, not a paraphrase of job names.

**`ci.yml`** runs on push to `main`/`develop`/`feature/**` and on PRs into
`main`/`develop`:

- `python-lint` — `ruff check` + `mypy --ignore-missing-imports` across all
  6 Python services plus `shared-python`.
- `python-test` — per-service pytest against real Postgres
  (`timescale/timescaledb:2.14.2-pg16`) and Redis service containers, with
  `--cov-fail-under=80` enforced per service.
- `shared-python-test` — pytest for `packages/shared-python/tests/`.
- `shared-ts-test` / `frontend-test` — type-check + test + build for
  `packages/shared-ts` and for `web-customer`/`web-admin` (these will stop
  being relevant once those apps are replaced).
- `migration-check` — `alembic upgrade head`, `downgrade -1`,
  `upgrade head` again against a clean Postgres, to catch a broken
  migration chain.
- `hard-gate-test` — runs `apps/gateway/tests/test_hard_gate.py`
  specifically, as its own job after `python-test`.
- `codeql` — CodeQL static analysis for Python and JS/TS.
- `docker-build` — builds every service's image (no push) and scans it
  with Trivy (`CRITICAL,HIGH`, results uploaded to the Security tab; the
  scan itself never fails the build — `exit-code: "0"`).
- `terraform-validate` — `terraform fmt -check`, `terraform init
  -backend=false`, `terraform validate`, and `tflint` across
  `infra/terraform/bootstrap` and both environments. This validates syntax
  and internal consistency only — it never applies anything and never
  touches a real backend/state.

**`build-and-push.yml`** runs on push to `main`/`develop`, and only if
`secrets.AWS_ACCESS_KEY_ID` is set (i.e. it's a no-op in a fork or an
un-configured repo): detects which services changed
(`dorny/paths-filter`), builds and pushes each changed service's image to
ECR, deploys to an EKS `staging` cluster (`sk-staging`) via
`kustomize`/`kubectl apply -k`, runs `tests/smoke/test_health.py` against
`https://staging-api.sahulatkar.com`, and on `main` only, deploys to an EKS
`production` cluster (`sk-production`) behind a GitHub `environment:
production` gate. Whether this workflow has ever actually run to
completion (i.e. whether `sk-staging`/`sk-production` clusters and DNS
genuinely exist) can't be confirmed from the repo alone — see Section 6.

---

## 6. Deployment Infra (Terraform / K8s)

Not relevant to building a frontend against a running backend — included
only for an honest picture of what exists.

**Terraform** (`infra/terraform/`): a `bootstrap/` stack plus `staging` and
`production` environment stacks, each composing real, non-trivial modules —
`vpc`, `eks`, `rds`, `elasticache`, `iam` (including per-service IRSA roles
for AWS Secrets Manager access), `kms`, `s3`, `ecr`, `pgbouncer` (ECS
Fargate), and `dns` (Route53 + cert-manager DNS-01 IRSA). This reads as
real infrastructure-as-code, not a stub — e.g. the staging stack wires up
per-service Secrets Manager IAM policies scoped to
`secret:{service}/{staging|prod}/*`, and a two-node-group EKS layout
(`general` on `t3.medium`, a tainted `playwright` pool on `m6i.2xlarge` for
checkout-automation workloads). The default AWS region across
`variables.tf` is `ap-south-1` (also the default in `.env.example`).

What can't be confirmed from the repo: whether this has ever been applied
against a real AWS account. There's no `.tfstate` or `.tfvars` checked in
(only `*.tfvars.example` / `backend.hcl.example` files — real values would
live outside this repo, e.g. in an S3 backend per environment), and CI's
`terraform-validate` job only runs `validate`/`fmt`/`tflint` with the
backend disabled — it never plans or applies. Treat this as "real Terraform
that should work" rather than "confirmed live infrastructure."

**Kubernetes** (`infra/k8s/`): a Kustomize `base/` with a deployment,
service, HPA, and (for most services) a PodDisruptionBudget per
microservice, plus `network-policies/` (default-deny + explicit per-service
allow rules), `monitoring/` (Prometheus + a Grafana golden-signals
dashboard), `logging/` (Loki + Fluent Bit), a `migration-job.yaml`, and
`overlays/staging` and `overlays/production` (ingress, cert-manager
`ClusterIssuer`, resource quotas, staging-only HPA min-replica patch). This
also reads as genuinely built out, not scaffolding — but like Terraform,
whether it's ever been `kubectl apply`'d against a real cluster isn't
verifiable from the repo itself; `build-and-push.yml` is the only thing
that would do so, gated on AWS credentials being present in the repo's
secrets.

**Bottom line for a new team member**: don't assume a live AWS environment
exists or matches this code exactly. If you need a backend to build
against, use the Docker Compose stack in Section 2 — it's the one thing in
this repo that's unambiguously real and runnable today.
