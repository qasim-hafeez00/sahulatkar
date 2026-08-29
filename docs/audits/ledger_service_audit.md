# Ledger Service: Integration Reference

**Service path:** `apps/ledger-service/` · **Last verified:** 2026-08-28 · **Test status:** 150 passed, 1 pre-existing unrelated failure (`test_reconciliation_import_accepts_valid_internal_token`, an enum-value mismatch, not a regression)

> This service has **no customer-facing endpoints**. Every route requires either an admin actor context or an internal-service token (see [Auth Model](#auth-model--critical-for-a-new-frontend) below — read this before building any admin finance UI against it).

---

## 1. Service Overview & Scope

The **Ledger Service** is the double-entry bookkeeping system of record for SahulatKar. It owns:

1. **Double-entry accounting** — every payment, purchase, late fee, charity disbursement, reversal, and manual adjustment is posted as a balanced journal entry (debits == credits, enforced at both the application layer and a Postgres trigger).
2. **Billing sweep** — daily job that triggers due installment collection and applies late fees to newly-overdue installments.
3. **Charity routing** — 100% of late fee revenue is tracked as a liability (`charity_payable`) and disbursed to Edhi Foundation via a periodic sweep, never recognized as company revenue.
4. **Reconciliation** — matches gateway settlement files against internal `PaymentTransaction` records.
5. **TASDEEQ reporting** — generates the Pakistani credit-bureau CSV submission format for loan reporting.
6. **Finance/admin reporting APIs** — P&L, trial balance, balance sheet, shariah audit report, account ledgers (T-accounts), journal entry browsing.

Ledger-service does **not** own: checkout UX, product extraction, contract generation/signing, payment gateway integration, or credit scoring. It reacts to events/calls from Payment Orchestrator and Gateway; it never initiates a purchase or payment itself.

It relies on the shared ORM models in `packages/shared-python/sk_shared/models/ledger.py` rather than defining its own — there is no `src/models/` content beyond a package marker.

---

## 2. Auth Model — critical for a new frontend

Every route in this service authenticates via **plain, unsigned request headers**, read in `src/core/dependencies.py`:

| Header | Purpose |
|---|---|
| `X-Actor-Type` | Must be exactly `admin` for any admin/finance endpoint — anything else is rejected with 403 `ADMIN_ROLE_REQUIRED`. |
| `X-Actor-Id` | Free-text actor identifier, recorded for audit purposes only. |
| `X-Actor-Roles` | Comma-separated role list (e.g. `finance_analyst,super_admin`) checked against each endpoint's required-role set. |
| `X-Request-ID` | Propagated for tracing; not auth-related. |
| `X-Internal-Token` | Required on internal-only routes (e.g. reconciliation import), compared with `hmac.compare_digest` against `settings.internal_api_token`. |

**There is no JWT verification, no signature, and no cryptographic binding between these headers and any real identity.** Anyone who can reach this service's HTTP port with `X-Actor-Type: admin` and `X-Actor-Roles: super_admin` gets full write access to the general ledger — including creating manual journal entries and reversing existing ones.

As of this writing, **Gateway's `admin_finance.py` does not proxy to this service** — it implements its own separate finance queries directly against the DB. That means nothing in the current codebase performs JWT-to-header translation for you. Before building any admin finance UI against Ledger Service directly:

- Either put Ledger Service behind Gateway (add a proxy layer in `admin_finance.py` that verifies the admin's JWT and then sets these headers itself, server-side, never trusting a client-supplied value), or
- Ensure network-level isolation (this service is not reachable from the public internet, only from a trusted internal network/ingress that sets these headers after its own auth check).

**Do not build a frontend that sends `X-Actor-*` headers directly from the browser.** That would let any authenticated (or unauthenticated) HTTP client impersonate `super_admin`.

Two role tiers are used throughout: `finance_analyst` (read access to most reporting) and `super_admin` (required for every write: manual entries, reversals, period close/reopen).

---

## 3. API Endpoint Catalog

### `src/api/v1/entries.py` — prefix `/entries` (roles: read = `finance_analyst`/`super_admin`, write = `super_admin` only)

| Method & Path | Purpose | Notes |
|---|---|---|
| `GET /entries/` | List journal entries, cursor-paginated. | Query params: `from_date`, `to_date` (`YYYY-MM-DD`), `entry_type`, `source_type`, `cursor`, `limit` (1-200, default 50). |
| `GET /entries/{entry_number}` | Full detail for one entry, including all posting lines. | 404 `ENTRY_NOT_FOUND` if missing. |
| `POST /entries/manual` | Create a manual journal entry. | Body: `{description, lines: [{account_code, debit_amount, credit_amount, description}], entry_date?, reference?}`. Supports `Idempotency-Key` header (used as `reference` if none given). Rejected with 400 if lines don't balance or reference an unknown account. |
| `POST /entries/{entry_number}/reverse` | Reverse an existing entry (creates an offsetting entry, doesn't mutate the original). | Body: `{reason, reversal_id?, entry_date?}`. `Idempotency-Key` header supported. 404 `ORIGINAL_ENTRY_NOT_FOUND` if the target doesn't exist. |

### `src/api/v1/accounts.py` — prefix `/accounts` (role: `finance_analyst`/`super_admin`)

| Method & Path | Purpose |
|---|---|
| `GET /accounts/` | List all GL accounts with current balances. Optional `account_type` filter (`asset|liability|equity|revenue|expense`) and `as_of` date. |
| `GET /accounts/{account_code}` | Single account's balance detail. 404 if unknown code. |
| `GET /accounts/{account_code}/ledger` | Full T-account view (every posting line touching this account), cursor-paginated with `from_date`/`to_date`. |

### `src/api/v1/periods.py` — prefix `/periods` (read: `finance_analyst`/`super_admin`; write: `super_admin` only)

| Method & Path | Purpose |
|---|---|
| `GET /periods/` | List accounting periods and their status (open/closed), `limit` up to 100. |
| `POST /periods/{period_key}/close` | Close a period — blocks further postings into it. Body: `{closed_by}`. |
| `POST /periods/{period_key}/reopen` | Reopen a closed period. Use with caution — no business-rule guard beyond the role check. |

### `src/api/v1/finance.py` — prefix `/admin/finance` (roles vary by endpoint — check each; all require `X-Actor-Type: admin`)

| Method & Path | Purpose |
|---|---|
| `GET /admin/finance/pl` | Profit & loss report for a period. |
| `GET /admin/finance/trial-balance` | Trial balance snapshot. |
| `GET /admin/finance/balance-sheet` | Balance sheet snapshot. |
| `GET /admin/finance/reconciliation` | Query reconciliation history/status. |
| `POST /admin/finance/reconciliation` | Import a reconciliation snapshot (gateway settlement file). Internal-token gated in addition to admin role. |
| `GET /admin/finance/shariah-audit` | Shariah compliance audit report — profit-vs-Murabaha-disclosure checks, charity allocation totals. |
| `GET /admin/finance/charity-report` | Charity disbursement summary, grouped by organization. |
| `POST /admin/finance/charity-disbursement` | Manually trigger/record a charity disbursement. |

### `src/api/v1/health.py` — prefix `/health` (no auth)

| Method & Path | Purpose |
|---|---|
| `GET /health/live` | Liveness — process is up. |
| `GET /health/ready` | Readiness — checks DB, Redis, seeded ledger accounts, active charity config, and event-listener/watchdog health. Returns structured per-dependency status. |

All response shapes are defined as Pydantic models in `src/schemas/finance.py` and `src/schemas/common.py` (pagination envelope) — read those directly for exact field names/types when generating a typed client.

---

## 4. Business Rules a Frontend Must Respect

- **Balance invariant**: every journal entry's debit lines must sum to its credit lines. This is enforced in `AccountingService` (application layer) *and* by a Postgres trigger on `journal_entry_lines` (`test_journal_entry_lines_balance_trigger.py` verifies this at the DB level) — an unbalanced manual entry is rejected with a 400, not silently accepted.
- **Manual entry guardrails**: `test_manual_entry_guardrails.py` covers a real control here — a manual admin entry cannot credit the `late_fee_collections` (revenue) account in a way that would misclassify what should be a charity liability. If you're building a manual-journal-entry UI, surface account codes/types clearly (`asset|liability|equity|revenue|expense`) so an operator can't blindly misclassify a posting.
- **Period close**: once a period is closed, no new postings land in it (enforced in `src/domain/period_rules.py`). A finance UI should show period status prominently before allowing any manual entry dated into that period.
- **Idempotency**: `POST /entries/manual` and `POST /entries/{entry_number}/reverse` both honor an `Idempotency-Key` header — always send one from the frontend for any user-triggered write, to make retries/double-clicks safe.
- **Charity money is never revenue**: late fees post to `charity_payable` (a liability), not to any revenue account, until an explicit disbursement moves it to a paid/disbursed state. Any dashboard summarizing "revenue" must exclude this by construction — don't sum it in ad hoc.

---

## 5. File Registry

### API (`src/api/v1/`)
`entries.py`, `accounts.py`, `periods.py`, `finance.py`, `health.py` — see endpoint catalog above.

### Services (`src/services/`)
| File | Purpose |
|---|---|
| `accounting_service.py` | Core double-entry engine — every `record_*` posting method (down payment, purchase, installment, late fee, charity disbursement, VCN load, merchant payment, gateway fee, refund, chargeback, provision, write-off, manual adjustment, reversal) plus reporting builders (P&L, trial balance, balance sheet, shariah audit). |
| `balance_service.py` | Computes/snapshots per-account balances (backs `GET /accounts/*` and the nightly snapshot worker). |
| `period_service.py` | Period lifecycle — get-or-create, close, reopen; delegates rule enforcement to `src/domain/period_rules.py`. |
| `late_fee_service.py` | Applies/waives late fees on installments, delegates the actual posting to `AccountingService`. |
| `charity_service.py` | Charity summaries, disbursement recording, marks `LateFeeCharityAllocation` rows disbursed. |
| `reconciliation_service.py` | Imports and queries settlement reconciliation snapshots (JSONL-persisted). |
| `tasdeeq_service.py` | Builds and submits TASDEEQ CSV reports (`batch_csv` local outbox or `http` mode with retry). |
| `tasdeeq_validation.py` | Strict schema validation for the TASDEEQ CSV format against the bureau's spec. |

### Workers (`src/workers/`, CLI entrypoints — run as separate processes/cron)
| File | Purpose |
|---|---|
| `billing_sweep_worker.py` | Daily due-installment collection + late-fee application, Redis-lock-guarded against concurrent runs. |
| `charity_disbursement_worker.py` | Periodic sweep that auto-disburses pending late-fee charity allocations older than a configured minimum age. |
| `balance_snapshot_worker.py` | Nightly per-account balance snapshotting via `BalanceService`. |
| `reconciliation_worker.py` | Reconciliation snapshot import entrypoint. |
| `tasdeeq_worker.py` | TASDEEQ report generation/submission entrypoint. |
| `dlq_worker.py` | Consumes the ledger dead-letter queue (JSONL-backed), retries failed events by re-publishing to Redis, alerts when DLQ depth exceeds threshold. |

### Core (`src/core/`)
`database.py` (async engine/session — see the PgBouncer note below), `dependencies.py` (auth headers, see section 2), `event_listeners.py` (Redis pub/sub consumer for `payment.down_payment_confirmed`, `order.purchase_confirmed`, `delivery.status_changed`), `middleware.py`, `logging.py`, `period_utils.py`, `readonly_guard.py`.

---

## 6. A Bug Worth Knowing About If You Touch This Service

`src/core/database.py`'s async engine was, until 2026-08-28, missing `connect_args={"statement_cache_size": 0}`. Every other service's DB engine (via the shared `packages/shared-python/sk_shared/database.py`) already had this. Without it, this service's connections — which route through PgBouncer in transaction-pooling mode — intermittently hit `asyncpg.exceptions.DuplicatePreparedStatementError`, silently failing real financial event postings (down payments, installments, late fees) in any deployment behind PgBouncer. It's fixed now, but if this file is ever refactored to create its own engine again (rather than importing the shared one), this flag must travel with it. This bug was invisible to the SQLite-backed unit test suite and was only found by running the full stack live against real Postgres — see `tests/e2e/README.md` for how that test works.

Relatedly, migrations `089`–`091` added several columns to `ledger.py` models (`journal_entries.source_reference/currency/reversed_by_id`, `ledger_accounts.parent_code/account_group/currency/is_control`, `ledger_periods.fiscal_year/pre_close_snapshot_at/reopened_at/reopened_by`, `late_fee_charity_allocations.journal_entry_id`, `journal_entry_lines.currency`, `ledger_account_balances.updated_at`) that existed as SQLAlchemy model fields but had never actually been migrated onto the real schema. If a real Postgres deployment ever throws `UndefinedColumnError` on a ledger table, check for this class of drift first — compare the model in `sk_shared/models/ledger.py` against `\d <table>` on the real DB rather than assuming the ORM and schema agree.

---

## 7. Tests

150 passing, one pre-existing unrelated failure (see header). Coverage includes: balanced-entry enforcement (app layer + DB trigger), manual entry guardrails, billing sweep locking/idempotency, overdue processing, charity lock/disbursement worker, DLQ worker, period close/reopen rules, reconciliation import/query, TASDEEQ submission modes and retries, unauthenticated-request rejection on every admin router, health/metrics endpoints, and end-to-end functional ledger flows. Test fixtures (`tests/conftest.py`) use `fakeredis` and an async SQLite fallback (`LEDGER_TEST_DATABASE_URL`) — meaning **Postgres-specific behavior (triggers, PgBouncer interaction, real constraint enforcement) is not exercised by this suite**; the E2E suite (`tests/e2e/`) is what actually validates this service against real Postgres.

---

## 8. Local Development

Runs as part of the full stack via `docker compose` at `infra/docker/docker-compose.yml` (Redis logical DB 4, prefixed by `sk:` key namespaces same as every other service). See `tests/e2e/README.md` for the exact commands to bring up the whole backend locally and a worked example of calling `GET /entries/` with the correct headers against a live stack.
