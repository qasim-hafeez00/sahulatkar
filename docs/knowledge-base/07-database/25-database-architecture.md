# Database Architecture

**Status:** STABLE — sourced from `docs/System-md-files/00Sahulatkar-System.md`, `docs/DATABASE_GUIDE.md`, and the per-module DB sections.

## Engine and scale

PostgreSQL 16, RDS `r6g.xlarge` (32GB) in production, with a co-located TimescaleDB extension for time-series data (delivery tracking events). Per the platform quick-reference: **169 tables across 13 domains**. Migration state per the last audit: 49 migrations present (001–049), sequence complete but most lack a working `downgrade()` (rollback), which is itself a listed gap (`DB-GAP-01`).

## Connection pooling

PgBouncer in transaction-mode, sized for 2,000 client connections down to 180 actual PostgreSQL connections. Local development connects directly via `sk_admin`/`localdev123` on `localhost:5432` — see `docs/DATABASE_GUIDE.md` for local dev credentials and roles (`sk_migrations` superuser for Alembic, `sk_app` for the main backend, `sk_admin_api` for the admin backend, `sk_app_readonly` for reporting).

## Key design rules (platform-wide, immutable per engineering docs)

- **All monetary fields are `DECIMAL(14,2)` — never `FLOAT`.** This is listed as an immutable rule in `docs/MASTER_PLAN.md`.
- **Dual primary key strategy:** every entity has a `BIGSERIAL` internal primary key plus a `UUID` external identifier (`gen_random_uuid()`), so external references never leak sequential internal IDs.
- **Soft deletes:** `deleted_at TIMESTAMP` on all customer-facing tables — hard deletes are avoided for audit/compliance reasons.
- **Audit trail:** `AFTER INSERT/UPDATE/DELETE` triggers on 30 sensitive tables, writing to `audit_trails`. **Known gap:** `audit_trails` itself is a normal (deletable) table, not an append-only/immutable store — flagged as not forensics-ready (`INF-GAP-08`); recommend moving to an immutable S3-backed or CloudWatch Logs-backed store.
- **Encryption:** `pgcrypto` AES-256 for CNIC, IBANs, VCN PAN/CVV/expiry, and MFA secrets — applied at the column level, not full-disk encryption alone.
- **Partitioning:** `orders` and `payment_transactions` partitioned quarterly by `created_at`; `audit_trails` monthly; `scraping_jobs` monthly.

## Ownership by service

See [`../05-architecture/21-service-responsibility-matrix.md`](../05-architecture/21-service-responsibility-matrix.md) for the service-to-table mapping. Each service is the sole writer for its domain's tables even though all services share one PostgreSQL instance (no per-service database split) — this is a deliberate DDD-bounded-context choice enforced by convention/code review, not by physical database isolation.

## Materialized views

`mv_daily_revenue` (GMV, gross profit, AOV per day), `mv_loan_portfolio` (status counts, outstanding totals, defaults), `mv_merchant_performance` (orders, GMV, checkout success rate per tracked merchant) — refreshed nightly, feeding the admin analytics dashboard.

## Critical indexes worth knowing about

- `installments(due_date, user_id) WHERE status='pending'` — a partial index that makes the daily billing sweep run in under 60 seconds over 100K rows. This is called out explicitly in source docs as *the* critical index for the platform's core recurring job.
- **Known gap:** `risk_blacklist(type, value)` has no index, so every blacklist check during request processing does a full table scan (`DB-GAP-05`) — a performance risk that will worsen with data volume.

## Known migration/schema gaps (from the 2026-04-27 audit)

- `system_parameters` table exists (checked at Gateway startup) but has **no seed migration** populating required defaults (min down payment %, max credit limit, late fee daily rate) — the table exists but is empty, so the "configurable via admin" story throughout this knowledge base is aspirational until this is fixed (`DB-GAP-04`).
- Trigger definitions use raw DDL with no version tracking — modifying a trigger requires a fresh migration with `CREATE OR REPLACE`, and there's no trigger-level test coverage (`DB-GAP-03`).
- `period_service.py`'s `create_period()` does not set `fiscal_year`, which needs either a non-null migration constraint or an application-layer fix (`DB-GAP-07`).

## Related documents

[`26-database-dictionary.md`](26-database-dictionary.md), [`../05-architecture/20-system-architecture.md`](../05-architecture/20-system-architecture.md), `docs/DATABASE_GUIDE.md` (local dev connection guide, kept in place rather than duplicated here since it's operational/credentials content, not architecture).
