# SahulatKar End-to-End Test Suite

Real, cross-service, order-lifecycle test that runs against the **full**
`docker compose` stack: gateway, product-service (+ its scraping/checkout/
vcn-verifier workers), credit-engine, payment-orchestrator, ledger-service,
notification-service, real Postgres, real Redis, and a small mock-merchant
fixture that stands in for a real e-commerce site. No service is mocked out
inside the test process itself -- every request in `test_order_lifecycle.py`
goes over real HTTP to a real container.

This is the first (and, as of this writing, only) cross-service/E2E test in
the repo. `tests/smoke/test_health.py` only checks `/health` against staging
URLs and isn't run in CI; this suite is meant to catch the class of bug unit
tests structurally cannot see -- wrong field names between services, timing
assumptions, event contracts two services disagree on.

## What it covers

One connected flow, in `test_full_order_lifecycle`:

1. Register a new customer (OTP flow; `dev_otp` is returned directly in
   local env).
2. KYC: start -> upload CNIC front/back + liveness video -> submit ->
   auto-approved (NADRA/OCR/liveness mocks all pass in local env).
3. Initiate an order against the mock-merchant's product page. This drives
   the **real** extraction pipeline: product-service fetches the page over
   HTTP, parses its schema.org JSON-LD (`html_scraper.py`'s Tier 2B path,
   no LLM/API key involved), calls back to gateway, which reserves credit.
4. Poll the offer until it's `ready`; accept it.
5. Generate + sign the Wakalah (agency) contract, then the Murabaha (sale)
   contract, both via the OTP-sign flow, taking the order to
   `contracts_signed`.
6. Pay the down payment via Payment Orchestrator directly (JazzCash,
   synchronous path) using the `ALLOW_TEST_PAYMENT_FALLBACKS` deterministic
   test-mode fallback (see below) instead of a real payment sandbox.
7. Poll for VCN (virtual card number) issuance.
8. Simulate the one Stripe Issuing webhook signal a real charge at the
   merchant would produce (see "Real bug found and fixed" below for why this
   step exists and is simulated rather than organic).
9. Wait for the **real** Playwright checkout automation
   (`form_filler.py::run_checkout`) to run against the mock merchant --
   navigate, add to cart, guest checkout, fill the form, submit -- and reach
   a terminal state.
10. Verify against the mock merchant's own `/_debug/submissions/<id>`
    endpoint that a real browser really filled in and submitted a real form
    (email, city, total, last-4 of the card).
11. Query ledger-service's real journal entries for the down payment and
    assert it's a real, balanced (debits == credits) posting.

## Running it

```bash
# from the repo root
docker compose -f infra/docker/docker-compose.yml \
                -f infra/docker/docker-compose.e2e.yml \
                up -d --build
pytest tests/e2e/ -v
```

Or just run pytest directly -- `tests/e2e/conftest.py`'s `docker_stack`
fixture does the build/up/migrate/health-wait dance itself and tears the
stack down (`down -v`) at the end of the session:

```bash
pytest tests/e2e/ -v -s
```

Requirements: Docker Desktop running, and enough free disk/RAM for the full
stack (product-service's image bundles Playwright + Chromium; the first
build downloads ~300MB of browser binaries and can take several minutes).
`asyncpg` and `httpx` must be installed in the Python environment running
pytest (both are dev dependencies already used elsewhere in this repo).

### Why `docker compose build <services>` then `up -d` (not `up -d --build`)

`docker-compose.yml`'s `product-service-scraping-worker`,
`-checkout-worker`, `-vcn-verifier`, `-price-staleness-worker`,
`-dlq-monitor`, and `-execution-reaper` services all set
`image: docker-product-service`, intentionally reusing product-service's own
build rather than building their own image (the pyproject.toml worker
console-scripts were never actually installed into the image -- see the long
comment above `product-service-scraping-worker` in that file). They also
inherit an *anonymous* `build: {context: ../../}` from the
`x-python-service` YAML anchor, with no `dockerfile:` path. That's harmless
as long as nothing ever asks Compose to build them directly -- but `up -d
--build` unconditionally tries to build every service that has a `build:`
section, including these, and fails immediately (`open Dockerfile: no such
file or directory`). `tests/e2e/conftest.py`'s `docker_stack` fixture works
around this by building only the services with a real, complete Dockerfile
(`docker compose build gateway product-service credit-engine
payment-orchestrator ledger-service notification-service e2e-mock-merchant`)
and then running `up -d` **without** `--build` for the full service list --
by then every image tag the worker services reference already exists
locally, so Compose starts them without attempting to build anything. This
mirrors the project's own `Makefile` (`make up` never passes `--build`
either). See the comments in `docker-compose.e2e.yml` and
`tests/e2e/conftest.py` for the full trace of this.

### Project name

The fixture pins the Compose project name to `docker` (`docker compose -p
docker ...`). This is required, not incidental: the worker services'
`image: docker-product-service` reference only resolves for free when the
project name is exactly `docker` (Compose's default image tag for a built
service with no explicit `image:` is `<project>-<service>`), and every
service in the base compose file has a **fixed** `container_name:` (e.g.
`sk-postgres`, `sk-gateway`) that would collide with an existing stopped
container of the same name under a different project anyway. `up -d`
recreates those containers in place if they already exist (stopped or
running) from a previous run under the same project; the session-end `down
-v` fixture cleanup removes the containers, network, and named volumes it
created.

## Real bugs found and fixed while building this suite

**VCN charge verification was fully disconnected (dead code) — every real
checkout, in every environment, terminated at `hitl_escalated` instead of
`succeeded`.**

`product-service`'s `VcnVerifier.verify_charge()` polls a Redis key
(`sk:vcn:charge:confirmed:{vcn_id}`) to know when a VCN was actually charged
at the merchant, before `VcnVerificationWorker` will mark a
`PurchaseExecution` as `succeeded`. Tracing every code path that could set
that key (or its legacy alias) turned up **zero writers anywhere in the
repository** -- including the one real production signal for it, Stripe's
`issuing_transaction.created` webhook
(`VcnOrchestrator.handle_stripe_event`, called from both
`payment-orchestrator`'s direct `/api/v1/webhooks/stripe` endpoint and the
Gateway-relay `payment_webhook_consumer` worker). That handler set
`VirtualCard.is_used = True` and queued an unconsumed `vcn.charged` outbox
event, but never touched the Redis key the verifier actually polls. The
practical effect: `VcnVerificationWorker` always times out
(`VCN_VERIFICATION_TIMEOUT_SECONDS`, default 120s) and every checkout lands
on `hitl_escalated`, even on a real Stripe webhook in a real environment --
this was not specific to the E2E/local-stub setup.

Fixed minimally in `apps/payment-orchestrator/src/orchestration/vcn_orchestrator.py`
(`VcnOrchestrator` now accepts an optional `redis` client and writes the
confirmation key in the `issuing_transaction.created` branch) and its two
call sites (`api/v1/webhooks.py`, `workers/payment_webhook_consumer.py`) so
both real webhook entry points now actually deliver the signal.

This alone doesn't make the *E2E* test pass, though: this sandbox has no real
Stripe integration for a webhook to organically come from (the VCN here is a
local stub card, and mock-merchant is a plain HTML form, not a real
card-network acquirer). So step 8 of the test simulates exactly one
`issuing_transaction.created` event via a direct POST to
payment-orchestrator's own `/api/v1/webhooks/stripe` endpoint -- the same
thing a real Stripe test-mode integration test would do with `stripe
trigger`. Signature verification is legitimately skipped there only because
`STRIPE_WEBHOOK_SECRET` is unset **and** `ALLOW_TEST_PAYMENT_FALLBACKS=true`
(pre-existing code in that handler), the same explicit, fail-closed-elsewhere
opt-in pattern already used for the JazzCash/SafePay/Raast adapters -- no
security control was weakened or bypassed to make this test pass.

**Compose project-name / image-tag fragility** (see "Why `docker compose
build` then `up -d`" above) -- not a runtime bug, but genuinely broke
bringing the stack up with the exact command this suite (and the task that
produced it) was told to use. Fixed by pinning `product-service`'s image tag
explicitly in `docker-compose.e2e.yml` (decouples correctness from the
Compose project name / invocation directory) and having the test fixture
build then `up` instead of `up --build`.

**`prohibited_merchant_domains` table was never created by any migration --
every real `POST /products/extract` call 500'd on real Postgres.**
`ProhibitedCheckerService.check_url` (apps/product-service/src/services/
prohibited_checker.py) runs a raw `SELECT domain FROM
prohibited_merchant_domains ...` wrapped in a bare `except Exception: pass`.
SQLite (this repo's unit-test backend) tolerates the failing statement
silently; real Postgres does not forgive a failed statement inside an open
transaction -- the very next statement on that connection (the
`ProhibitedCategory` keyword check right after) failed too with
`InFailedSQLTransactionError`, uncaught, 500ing every extraction call in any
real environment. Fixed with two changes: migration 088 actually creates the
table (the feature was silently dead, not just fragile), and
`check_url` now wraps that query in a `db.begin_nested()` SAVEPOINT so a
failure there can never poison the rest of the request's transaction,
regardless of the underlying cause.

**Local `.env`'s `BRIGHTDATA_PROXY_URL` breaks every checkout automation
run, silently.** Not a code bug -- this developer machine's `.env` (loaded
via `env_file:` before `docker-compose.e2e.yml`'s overrides apply) had
`BRIGHTDATA_PROXY_URL=http://mock-proxy`, a placeholder that isn't a real
host. `form_filler.py::run_checkout` passes it straight to Chromium as
`--proxy-server=...` whenever it's set at all, so every `page.goto()`
timed out (`net::ERR_TIMED_OUT`) regardless of whether the target was
reachable. `docker-compose.e2e.yml` now force-blanks
`BRIGHTDATA_PROXY_URL` for the checkout worker so this suite is deterministic
regardless of what a developer's local `.env` happens to contain.

**VCN charge confirmation crossed a Redis logical-database boundary and was
silently unreachable.** Even after the `vcn_orchestrator.py` fix above,
`VcnOrchestrator` (payment-orchestrator) writes `sk:vcn:charge:confirmed:
{vcn_id}` on **its own** Redis client -- bound to `REDIS_URL`'s `db=3`
(`infra/docker/docker-compose.yml`). `VcnVerifier.verify_charge()`
(product-service) polls that exact key on **its own** client, bound to
`db=1`. Redis keys are namespaced per `SELECT`ed logical database; pub/sub
is not. Live-verified directly (`redis-cli -n 3 GET ...` vs `-n 1 GET ...`):
the key existed only in `db=3`, invisible to the poller in `db=1` -- so
every checkout timed out to `hitl_escalated` regardless of the earlier fix.
Fixed in `apps/product-service/src/workers/event_listener.py`: it now also
subscribes to `sk:events:vcn.charged` (pub/sub crosses DB boundaries, same
as the pre-existing `vcn.issued`/`order.cancelled` handling) and sets the
confirmation key locally, in its own `db=1`, where the poller that actually
reads it lives.

**`merchant_repository.py::recalculate_success_rate` had a real
`sk_shared.` schema-prefix bug on Postgres.** `sk_shared` is the Python
package the shared ORM models live in -- never a Postgres schema. Every
table lives in `public`. This raw-SQL stats update always raised
`UndefinedTableError` on real Postgres, silently rolling back the *entire*
enclosing transaction -- including `VcnVerificationWorker` marking a
checkout `succeeded`, which is what actually surfaced it (the checkout sat
at `pending_verification` forever even with charge confirmation correctly
delivered). The SQLite branch two lines down was already correctly
unprefixed; fixed to match.

**Six ledger ORM models were missing columns from the real schema --
`AccountingService` couldn't post a single real journal entry.**
Live-running the real down-payment flow surfaced these one table at a time
as more of the code path actually executed against real Postgres for the
first time; migrations 089-091 close out a full diff of every model in
`packages/shared-python/sk_shared/models/ledger.py` against a real,
fully-migrated schema:
- `journal_entries`: missing `source_reference`, `currency`, `reversed_by_id`
- `ledger_accounts`: missing `parent_code`, `account_group`, `currency`, `is_control`
- `ledger_periods`: missing `fiscal_year` (backfilled from `start_date`), `pre_close_snapshot_at`, `reopened_at`, `reopened_by`
- `late_fee_charity_allocations`: missing `journal_entry_id`
- `journal_entry_lines`: missing `currency`
- `ledger_account_balances`: missing `updated_at` (inherits `TimestampMixin`, which declares it)

**Most severe: ledger-service's own DB engine was missing the PgBouncer
prepared-statement fix every other service already has.**
`packages/shared-python/sk_shared/database.py`'s shared engine correctly
passes `connect_args={"statement_cache_size": 0}` -- required because
`infra/docker/docker-compose.yml` runs PgBouncer in `PGBOUNCER_POOL_MODE=
transaction`, under which a single logical connection can be handed
different backend Postgres connections between statements, so asyncpg's
client-side prepared-statement cache (keyed by name) can collide with
whatever the previous backend connection already had prepared. Every other
service imports that shared engine. `apps/ledger-service/src/core/
database.py` creates its **own** engine and never picked up the fix.
Effect, live-verified: `src/events/listener.py`'s real financial event
processing (down payment confirmation, installment payment, late fee) failed
unpredictably with `asyncpg.exceptions.DuplicatePreparedStatementError` --
not classified as transient by `_is_transient_error`, so the event was
dropped to the DLQ rather than retried. This means ledger postings for real
money movement could silently never happen, intermittently, in **any** real
Postgres+PgBouncer deployment -- not an E2E-only issue. Fixed by adding the
same `connect_args` to ledger-service's own engine.

## Files

- `conftest.py` -- session-scoped `docker_stack` / `base_urls` fixtures:
  brings the stack up, waits for Postgres healthy, runs Alembic migrations,
  waits for every service's `/health`, tears down (`down -v`) at session end.
  Fails fast with compose logs dumped on any timeout -- never hangs.
- `test_order_lifecycle.py` -- the connected order-lifecycle test described
  above.
- `fixtures/mock_merchant/` -- the mock merchant fixture (FastAPI app +
  Dockerfile) product-service's real extraction and checkout automation run
  against.
