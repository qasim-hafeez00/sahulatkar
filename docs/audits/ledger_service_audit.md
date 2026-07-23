# Ledger Service: Comprehensive Audit & Implementation Report

## 1. Service Overview & Scope

The **Ledger Service** (`apps/ledger-service/`) is the dedicated financial bookkeeping microservice in SahulatKar. It owns the double-entry ledger, billing sweep support, late-fee charity routing, reconciliation processing, TASDEEQ credit-bureau reporting, and finance/admin reporting APIs.

This audit is intentionally scoped to **ledger-service only**. Shared packages and database migrations are referenced only where they are directly required by the ledger service implementation.

### Core Responsibilities
1. **Double-entry accounting** for payment, purchase, late fee, charity disbursement, reversal, and adjustment workflows.
2. **Billing sweep** execution for due installments with distributed locking and overdue processing.
3. **Reconciliation** ingestion and reporting for gateway settlement data.
4. **TASDEEQ reporting** with local outbox or HTTP submission flow and durable submission audit.
5. **Charity routing** for late fees with 100% allocation compliance.
6. **Finance admin APIs** for profit/loss, trial balance, balance sheet, shariah audit, reconciliation, and charity reporting.
7. **Operational visibility** via request IDs, readiness checks, metrics, and listener health.

### Current Verified State
- Ledger-service tests currently pass in the workspace.
- Verified test count at the end of the latest implementation pass: **39 passed**.
- The microservice is now functionally implemented as a complete ledger bounded context in this repository.

---

## 2. Bounded Contexts and Design Decisions

### Ownership Boundaries
Ledger-service owns:
- Journal entry creation and balancing.
- Ledger reporting and finance admin endpoints.
- Billing sweep orchestration.
- Reconciliation status tracking.
- Charity disbursement ledgering.
- TASDEEQ report generation/submission.
- Event-driven posting for payments and purchase confirmations.

Ledger-service does **not** own:
- Customer-facing checkout UX.
- Product scraping/extraction.
- Contract generation/signing.
- Payment orchestration.
- Gateway routing.
- Credit scoring.

### Architectural Choices Already Implemented
- FastAPI app with lifespan-managed Redis and listener tasks.
- Async SQLAlchemy session usage.
- Request ID propagation middleware.
- Prometheus request metrics.
- Redis-based distributed lock for billing sweep.
- JSONL-based durable audit trails for reconciliation and TASDEEQ in this workspace.
- Fakeredis-backed tests with SQLite fallback for local execution.

---

## 3. Directory Structure & File Inventory

### Root Files
- `Dockerfile` - Container image definition for ledger-service.
- `pyproject.toml` - Python project metadata, dependencies, and pytest configuration.

### `src/` Overview
- `src/config.py` - Runtime settings for database, Redis, billing/reconciliation crons, TASDEEQ modes, audit directories, and internal auth token.
- `src/main.py` - FastAPI app construction, lifespan management, listener startup/watchdog, health endpoint, and metrics endpoint.

### `src/api/`
- `src/api/routes.py` - Top-level API router inclusion for versioned endpoints.
- `src/api/v1/__init__.py` - Versioned API package marker.
- `src/api/v1/finance.py` - Finance/admin endpoints for reporting, reconciliation, and charity operations.
- `src/api/v1/health.py` - Live/ready health endpoints with dependency and listener status reporting.

### `src/accounting/`
- `src/accounting/accounts.py` - Canonical account code mapping and posting-line invariants.

### `src/billing/`
- `src/billing/__init__.py` - Billing package marker.
- `src/billing/billing_sweep.py` - Billing sweep orchestration, lock handling, payment triggering, overdue detection, and late-fee application.
- `src/billing/overdue_processor.py` - Overdue detection, batch status transitions, and late-fee amount policy.

### `src/core/`
- `src/core/database.py` - Shared async DB session/engine wiring.
- `src/core/dependencies.py` - Request context extraction, admin role enforcement, and internal token validation.
- `src/core/event_listeners.py` - Redis pub/sub listener for ledger-relevant events.
- `src/core/logging.py` - Logging configuration for service startup.
- `src/core/middleware.py` - Request ID middleware and HTTP request metrics.

### `src/models/`
- `src/models/` - Present as a package directory; ledger-service relies primarily on shared models from `packages/shared-python/sk_shared/models/` rather than defining new ORM models locally.

### `src/schemas/`
- `src/schemas/__init__.py` - Schema package exports.
- `src/schemas/common.py` - Shared pagination response schema.
- `src/schemas/finance.py` - Finance, reconciliation, balance sheet, charity, and TASDEEQ request/response schemas.

### `src/services/`
- `src/services/accounting_service.py` - Core ledger posting and financial reporting service.
- `src/services/charity_service.py` - Charity summary and disbursement service.
- `src/services/late_fee_service.py` - Late-fee application, waiver, and summary service.
- `src/services/reconciliation_service.py` - Reconciliation import/query service with durable snapshot persistence.
- `src/services/tasdeeq_service.py` - TASDEEQ report generation and submission service with audit trail and retries.

### `src/workers/`
- `src/workers/__init__.py` - Worker package marker.
- `src/workers/billing_sweep_worker.py` - CLI worker entrypoint for billing sweep execution.
- `src/workers/reconciliation_worker.py` - CLI worker entrypoint for reconciliation snapshot import.
- `src/workers/tasdeeq_worker.py` - CLI worker entrypoint for TASDEEQ report generation/submission.

### `tests/`
- `tests/conftest.py` - Shared test fixtures, Redis override, async DB setup, and seed helpers.
- `tests/test_accounting_completeness.py` - Regression coverage for expanded accounting journal workflows and reversals.
- `tests/test_billing_lock.py` - Billing lock and lock-release tests.
- `tests/test_finance_api.py` - Finance API authorization, reporting, reconciliation, charity, and health request ID tests.
- `tests/test_health_and_metrics.py` - Health endpoint and Prometheus metrics tests.
- `tests/test_late_fee_service.py` - Late-fee application and waiver behavior tests.
- `tests/test_ledger_functional.py` - End-to-end functional ledger flows.
- `tests/test_overdue_processor.py` - Overdue detection and late-fee policy tests.
- `tests/test_reconciliation_service.py` - Durable reconciliation snapshot and query tests.
- `tests/test_tasdeeq_service.py` - TASDEEQ submission mode and retry/audit tests.

---

## 4. File-by-File Implementation Audit

### 4.1 Root and Configuration

#### `apps/ledger-service/pyproject.toml`
- Declares the service as `sk-ledger-service`.
- Pins FastAPI, SQLAlchemy, asyncpg, Pydantic settings, Prometheus client, and shared package dependency.
- Test extras include pytest, pytest-asyncio, fakeredis, aiosqlite, httpx, and coverage tooling.
- Pytest is configured to use `src` as pythonpath and `tests` as the test root.

#### `apps/ledger-service/Dockerfile`
- Containerizes the ledger service for runtime deployment.
- Exposes the application port and follows the workspace's Python service conventions.

#### `src/config.py`
- Central settings model for the microservice.
- Contains:
  - `service_name`
  - `database_url`
  - `redis_url`
  - `redis_db`
  - `billing_sweep_cron`
  - `reconciliation_cron`
  - `tasdeeq_mode`
  - `tasdeeq_endpoint_url`
  - `tasdeeq_api_token`
  - `tasdeeq_timeout_seconds`
  - `tasdeeq_max_retries`
  - `tasdeeq_audit_dir`
  - `reconciliation_audit_dir`
  - `default_charity_registration_number`
  - `payment_service_url`
  - `internal_api_token`
- The service is configured for Redis DB 4.

---

### 4.2 API Layer

#### `src/api/routes.py`
- Composes the versioned API router.
- Includes the finance and health routers.

#### `src/api/v1/__init__.py`
- Marker package for versioned API resources.

#### `src/api/v1/finance.py`
- Implements all finance/admin endpoints.
- Uses role-based access checks and internal token checks.
- Exposes:
  - `GET /admin/finance/pl`
  - `GET /admin/finance/trial-balance`
  - `GET /admin/finance/balance-sheet`
  - `GET /admin/finance/reconciliation`
  - `POST /admin/finance/reconciliation`
  - `GET /admin/finance/shariah-audit`
  - `GET /admin/finance/charity-report`
  - `POST /admin/finance/charity-disbursement`
- Delegates business logic to accounting, reconciliation, and charity services.
- Uses explicit Pydantic response models from `src/schemas/finance.py`.

#### `src/api/v1/health.py`
- Exposes:
  - `GET /health/live`
  - `GET /health/ready`
- Readiness verifies:
  - Database connectivity
  - Redis connectivity
  - Seeded ledger accounts
  - Active charity configuration
  - Listener/watchdog task health
- Returns structured dependency and listener state.

---

### 4.3 Accounting and Journal Logic

#### `src/accounting/accounts.py`
- Central chart-of-accounts code mapping.
- Includes cash, AR installments, VCN issued, AP merchants, charity payable, customer deposits, owner equity, retained earnings, Murabaha profit, affiliate commission, late fee collections, merchant payment expense, gateway fees, VCN issuance, loan loss provision, and loan loss reserve.
- `PostingLine` now enforces:
  - non-negative values
  - exactly one side per line
  - at least one amount must be present

#### `src/services/accounting_service.py`
- Core double-entry engine for ledger-service.
- Implemented workflows:
  - `record_down_payment`
  - `record_purchase`
  - `record_installment_paid`
  - `record_late_fee`
  - `record_charity_disbursement`
  - `record_vcn_load`
  - `record_merchant_payment`
  - `record_gateway_fee`
  - `record_refund`
  - `record_chargeback`
  - `record_provision`
  - `record_write_off`
  - `record_manual_adjustment`
  - `record_reversal`
- Reporting functions:
  - `build_profit_loss_report`
  - `get_trial_balance`
  - `build_balance_sheet`
  - `build_shariah_audit_report`
- Internal safeguards:
  - balanced-entry validation
  - duplicate source detection
  - concurrency-safe journal numbering via UUID-based entry numbers
  - period parsing for year, month, and quarter inputs
- Late-fee charity logic is tied to ledger accounts and charity allocation records.

#### `src/services/late_fee_service.py`
- Applies late fees to installments.
- Supports waiver and summary reporting.
- Prevents duplicate fee application.
- Delegates posting to `AccountingService`.

#### `src/services/charity_service.py`
- Computes charity summaries and pending disbursements.
- Records charity disbursement ledger entries.
- Marks late-fee charity allocations as disbursed.
- Produces charity reporting grouped by organization.

---

### 4.4 Billing and Overdue Processing

#### `src/billing/__init__.py`
- Billing package marker.

#### `src/billing/billing_sweep.py`
- Executes the daily billing sweep.
- Uses a distributed Redis lock to prevent concurrent pod execution.
- Loads due installments.
- Calls payment orchestrator for installment triggering.
- Records successful installment payments in the ledger.
- Detects newly overdue installments.
- Applies late-fee processing through overdue and late-fee services.
- Returns structured sweep statistics.

#### `src/billing/overdue_processor.py`
- Finds newly overdue installments.
- Marks installments overdue in batch.
- Calculates late-fee amounts using the configured policy.
- Maintains in-session `days_overdue` values for predictability.

---

### 4.5 Reconciliation and TASDEEQ

#### `src/services/reconciliation_service.py`
- Imports reconciliation snapshots.
- Matches payment transactions by gateway and settlement date.
- Marks matched transactions as reconciled.
- Persists reconciliation snapshots and items to JSONL audit files under `settings.reconciliation_audit_dir`.
- Queries reconciliation history from persisted snapshots with pagination and filtering.
- Returns structured reconciliation status, totals, and discrepancy information.

#### `src/services/tasdeeq_service.py`
- Builds TASDEEQ report CSV output from loan and customer profile data.
- Supports two submission modes:
  - `batch_csv` / local file outbox
  - `http` / API submission with retries
- Writes durable JSONL submission audit records.
- Retries transient HTTP failures with backoff.
- Extracts remote submission references when present.
- Uses configured audit directory `settings.tasdeeq_audit_dir`.

---

### 4.6 Event Listener and Workers

#### `src/core/event_listeners.py`
- Subscribes to ledger-relevant pub/sub channels.
- Handles:
  - `payment.down_payment_confirmed`
  - `order.purchase_confirmed`
  - `delivery.status_changed`
- Posts ledger entries from event payloads.
- Uses defensive parsing and logs per-message failures without crashing the listener loop.

#### `src/workers/billing_sweep_worker.py`
- CLI entrypoint for running billing sweeps.
- Initializes Redis and passes it into `BillingSweepService`.
- Logs structured completion output.

#### `src/workers/reconciliation_worker.py`
- CLI entrypoint for reconciliation snapshot import.
- Logs structured completion output.

#### `src/workers/tasdeeq_worker.py`
- CLI entrypoint for TASDEEQ reporting.
- Delegates to `TasdeeqService`.
- Logs structured result metadata.

#### `src/workers/__init__.py`
- Worker package marker.

---

### 4.7 Core Infrastructure

#### `src/core/database.py`
- Shared async engine/session wiring for the service.
- Uses the ledger-service database URL from settings.

#### `src/core/dependencies.py`
- Extracts request context from headers.
- Enforces admin role requirements for finance/admin endpoints.
- Validates internal requests using a header token with constant-time comparison.
- Carries request ID and actor roles in the request context.

#### `src/core/logging.py`
- Configures standard service logging.

#### `src/core/middleware.py`
- Adds request IDs to incoming requests and response headers.
- Logs request metadata.
- Exposes Prometheus metrics counters and latency histograms.

#### `src/main.py`
- Bootstraps the FastAPI app.
- Starts the ledger event listener and watchdog task.
- Exposes `/health` and `/metrics`.
- Handles shutdown cleanup for Redis and listener tasks.

---

### 4.8 Schemas

#### `src/schemas/__init__.py`
- Aggregates public schema exports.

#### `src/schemas/common.py`
- Standard pagination response schema.

#### `src/schemas/finance.py`
- Request/response schemas for finance and reporting APIs.
- Includes:
  - reconciliation import models
  - profit/loss response
  - trial balance response
  - balance sheet response
  - reconciliation list response
  - shariah audit response
  - charity report/disbursement models

---

## 5. Tests and Verification

The ledger-service test suite is broad and currently green.

### Test Coverage Areas
- Core accounting postings and reversals.
- Billing sweep locking and overdue processing.
- Finance API authorization and reporting.
- Health and metrics endpoint behavior.
- Late-fee application and summary.
- Reconciliation persistence and query flow.
- TASDEEQ submission modes and retries.
- End-to-end functional ledger flows.

### Test Fixtures
- `tests/conftest.py` uses:
  - async SQLAlchemy test engine
  - `fakeredis` for Redis behavior
  - `app.state.redis` override
  - `LEDGER_TEST_DATABASE_URL` fallback to SQLite for local safety

### Verified Status
- Full suite last run in this workspace: **39 passed**.

---

## 6. Database and Migration Support

Ledger-service depends on a larger shared migration chain, but the ledger-specific and ledger-relevant migration support in this workspace includes:

- `db/migrations/versions/020_financial_accounting_remaining.py`
  - Reconciliation tables.
  - Gateway settlements.
  - Revenue transactions.
  - Financial report scaffolding.

- `db/migrations/versions/039_missing_db_objects.py`
  - Scheduled tasks table seeding.
  - Partition setup and shared operational DB objects.

- `db/migrations/versions/041_production_hardening.py`
  - Shared production hardening that impacts ledger-adjacent tables and constraints.

- `db/migrations/versions/042_ledger_scheduler_seeds.py`
  - Ledger scheduler seeds for the explicit billing and reconciliation crons defined by ledger-service.

### Ledger-Specific Migration Notes
- The ledger service currently uses JSONL audit persistence for reconciliation and TASDEEQ in this workspace.
- The scheduler seed migration registers only the tasks that are explicitly defined in ledger-service config.
- No undocumented TASDEEQ or charity cron was invented.

---

## 7. Runtime, Security, and Observability

### Security
- Admin endpoints require both admin actor headers and role checks.
- Internal reconciliation import validates an internal token.
- Request IDs are propagated through middleware and returned in response headers.
- The service avoids leaking raw internals in standard API responses.

### Observability
- `/metrics` is exposed for Prometheus scraping.
- Request count and latency metrics are recorded.
- Readiness checks include listener/watchdog state.
- Structured logs are emitted from middleware and worker entrypoints.

### Reliability
- Billing sweep uses a Redis distributed lock.
- Event listener exceptions are isolated per message.
- TASDEEQ HTTP submission retries transient failures.
- Reconciliation and TASDEEQ write durable JSONL audit records.

---

## 8. Implementation Completeness Assessment

### What Is Implemented
- Full accounting and ledger posting flow.
- Late-fee and charity compliance flow.
- Billing sweep and overdue processing.
- Reconciliation import/query flow.
- TASDEEQ submission/report generation flow.
- Health, readiness, metrics, logging, and request-ID support.
- Worker entrypoints for operational execution.
- Comprehensive tests with passing status.

### What Is Left
At this point, the remaining work is primarily deployment/environment coordination rather than missing ledger-service application code. Examples:
- External Postgres/Redis deployment wiring in non-local environments.
- Infrastructure task scheduling outside this repository's runtime execution.
- Any organization-specific ops policy changes not represented in code.

### Overall Status
**Ledger-service implementation status: functionally complete and verified in this workspace.**

---

## 9. Executive Summary

The Ledger Service is now a fully implemented microservice in this repository with clear ownership boundaries, complete finance/ledger workflows, verified health and metrics surfaces, production-oriented worker behavior, and a passing regression test suite. Anyone reading this audit should be able to understand:
- what the service owns,
- what each file does,
- how the service behaves at runtime,
- how it is tested,
- and what still depends on external deployment choices.

This document should be used as the ledger-service implementation reference for maintenance, review, and future hardening work.
