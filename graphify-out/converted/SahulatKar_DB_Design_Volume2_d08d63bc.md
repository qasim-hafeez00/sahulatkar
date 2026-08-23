<!-- converted from SahulatKar_DB_Design_Volume2.docx -->

SAHULATKAR
Database Architecture & Design — Volume II

Sections 16–25: Indexing, Partitioning, Security, DR, Performance,
Migration, Pakistan Considerations, Audit Logging & Cost Projections
Version 1.0  |  March 2026  |  CONFIDENTIAL

# 16. Part M: System & Integration Domain (Continued)
The previous volume covered api_keys and background_jobs. This section completes the domain with webhooks, integration audit logs, error tracking, and health metrics.
## 16.4 Table: webhooks
CREATE TABLE webhooks (
id                  BIGSERIAL PRIMARY KEY,
uuid                UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
name                VARCHAR(100) NOT NULL,
endpoint_url        VARCHAR(2048) NOT NULL,
secret_hash         VARCHAR(64) NOT NULL,   -- HMAC-SHA256 signing secret (hashed)
events              TEXT[] NOT NULL,        -- ['order.completed','payment.received']
owner_type          VARCHAR(20) NOT NULL CHECK (owner_type IN ('merchant_partner','internal')),
owner_id            BIGINT,
is_active           BOOLEAN NOT NULL DEFAULT TRUE,
retry_max           SMALLINT NOT NULL DEFAULT 5,
timeout_seconds     SMALLINT NOT NULL DEFAULT 30,
headers             JSONB,                  -- Custom headers per webhook
last_triggered_at   TIMESTAMP,
failure_count       INTEGER NOT NULL DEFAULT 0,
is_paused           BOOLEAN NOT NULL DEFAULT FALSE,
paused_reason       TEXT,
created_by          BIGINT,
created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
updated_at          TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_webhooks_owner ON webhooks(owner_type, owner_id);
CREATE INDEX idx_webhooks_active ON webhooks(is_active) WHERE is_active = TRUE;
## 16.5 Table: webhook_deliveries
CREATE TABLE webhook_deliveries (
id                  BIGSERIAL PRIMARY KEY,
webhook_id          BIGINT NOT NULL REFERENCES webhooks(id) ON DELETE CASCADE,
event_type          VARCHAR(100) NOT NULL,
event_id            UUID NOT NULL DEFAULT gen_random_uuid(),
payload             JSONB NOT NULL,
attempt_number      SMALLINT NOT NULL DEFAULT 1,
status              VARCHAR(20) NOT NULL DEFAULT 'pending'
CHECK (status IN ('pending','sending','delivered','failed','abandoned')),
response_code       SMALLINT,
response_body       TEXT,
duration_ms         INTEGER,
next_retry_at       TIMESTAMP,
sent_at             TIMESTAMP,
delivered_at        TIMESTAMP,
created_at          TIMESTAMP NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (created_at);

CREATE INDEX idx_wd_webhook ON webhook_deliveries(webhook_id, created_at DESC);
CREATE INDEX idx_wd_status ON webhook_deliveries(status) WHERE status IN ('pending','failed');
CREATE INDEX idx_wd_retry ON webhook_deliveries(next_retry_at) WHERE status = 'failed';
## 16.6 Table: integration_logs
-- All outbound third-party API calls: NADRA, Safepay, JazzCash, Stripe, AfterShip, etc.
CREATE TABLE integration_logs (
id              BIGSERIAL,
service_name    VARCHAR(50) NOT NULL,   -- 'nadra','safepay','jazzcash','stripe','aftership'
operation       VARCHAR(100) NOT NULL,  -- 'verify_cnic','charge_card','track_shipment'
request_id      UUID NOT NULL,
endpoint        VARCHAR(512),
method          VARCHAR(10),            -- 'POST','GET'
request_headers JSONB,                  -- Sanitized (no auth tokens)
request_body    JSONB,                  -- PII removed/masked
response_code   SMALLINT,
response_body   JSONB,
latency_ms      INTEGER,
is_success      BOOLEAN,
error_code      VARCHAR(50),
error_message   TEXT,
user_id         BIGINT,
order_id        BIGINT,
created_at      TIMESTAMP NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (created_at);

-- Weekly partitions (very high volume)
CREATE INDEX idx_intlog_service ON integration_logs(service_name, created_at DESC);
CREATE INDEX idx_intlog_request ON integration_logs(request_id);
CREATE INDEX idx_intlog_success ON integration_logs(is_success, service_name);
## 16.7 Table: error_logs
CREATE TABLE error_logs (
id              BIGSERIAL,
error_id        UUID NOT NULL DEFAULT gen_random_uuid(),
service         VARCHAR(50) NOT NULL,   -- 'api','worker','scraper','billing'
severity        VARCHAR(10) NOT NULL CHECK (severity IN ('debug','info','warn','error','fatal')),
error_code      VARCHAR(100),
message         TEXT NOT NULL,
stack_trace     TEXT,
context         JSONB,
user_id         BIGINT,
request_id      UUID,
environment     VARCHAR(20) DEFAULT 'production',
resolved        BOOLEAN NOT NULL DEFAULT FALSE,
resolved_at     TIMESTAMP,
created_at      TIMESTAMP NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (created_at);

CREATE INDEX idx_errlogs_sev ON error_logs(severity, created_at DESC);
CREATE INDEX idx_errlogs_svc ON error_logs(service, created_at DESC);
CREATE INDEX idx_errlogs_unresolved ON error_logs(resolved) WHERE resolved = FALSE;
## 16.8 Table: system_health_metrics
-- TimescaleDB hypertable for real-time operational metrics
CREATE TABLE system_health_metrics (
id              BIGSERIAL,
metric_name     VARCHAR(100) NOT NULL,
metric_value    DECIMAL(14,4) NOT NULL,
labels          JSONB,                  -- {service:'api', endpoint:'/orders'}
recorded_at     TIMESTAMP NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (recorded_at);

-- After creation, enable TimescaleDB compression for metrics older than 7 days:
-- SELECT add_compression_policy('system_health_metrics', INTERVAL '7 days');
-- SELECT add_retention_policy('system_health_metrics', INTERVAL '90 days');

CREATE INDEX idx_shm_name_time ON system_health_metrics(metric_name, recorded_at DESC);

-- Key metrics tracked:
-- api.response_time_ms, api.error_rate, scraper.success_rate
-- billing.installment_collection_rate, fraud.alert_count
-- db.query_time_p99, db.connection_pool_usage
## 16.9 Table: scheduled_tasks
CREATE TABLE scheduled_tasks (
id              SERIAL PRIMARY KEY,
task_name       VARCHAR(100) UNIQUE NOT NULL,
description     TEXT,
cron_expression VARCHAR(50) NOT NULL,
last_run_at     TIMESTAMP,
last_run_status VARCHAR(20) CHECK (last_run_status IN ('success','failed','running')),
last_run_duration_ms INTEGER,
next_run_at     TIMESTAMP,
is_enabled      BOOLEAN NOT NULL DEFAULT TRUE,
failure_count   SMALLINT NOT NULL DEFAULT 0,
updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Key scheduled tasks:
-- 'daily_installment_due_check'    - 0 8 * * *  (Check & notify due installments)
-- 'daily_overdue_escalation'       - 0 9 * * *  (Mark overdue, assign late fees)
-- 'hourly_vcn_expiry_check'        - 0 * * * *  (Void expired VCNs)
-- 'nightly_credit_review'          - 0 2 * * *  (Periodic credit limit reassessment)
-- 'monthly_archive_orders'         - 0 3 1 * *  (Move old orders to cold partition)
-- 'weekly_reconciliation'          - 0 4 * * 1  (Gateway settlement reconciliation)
-- 'daily_shariah_charity_transfer' - 0 10 * * * (Disburse accumulated late fee charity)
-- 'nightly_fraud_model_refresh'    - 0 1 * * *  (Reload fraud rules from DB to cache)
-- 'monthly_credit_bureau_report'   - 0 5 1 * *  (Submit PBCL report)

# 17. Comprehensive Indexing Strategy
A disciplined indexing strategy is the single highest-leverage performance lever for a BNPL platform. Every installment due date check, every fraud signal query, and every admin dashboard load depends on correct index design. The following documents every index across all 170+ tables, grouped by domain and query pattern.
## 17.1 Indexing Principles
Golden Rule: An index is a write penalty paid upfront for a read reward later. Every index slows INSERT/UPDATE. Only create indexes that serve identified query patterns with significant frequency (>100 executions/day) or latency criticality (<100ms SLA).
## 17.2 Critical Path Indexes — High-Frequency Queries
The following are the top 20 most frequently executed queries in SahulatKar's runtime, each with its supporting index design:
### Query Pattern 1: Installment Due Date Collection (runs hourly)
-- Query: Find all pending installments due today for billing
SELECT i.*, u.phone, u.email
FROM installments i
JOIN users u ON u.id = i.user_id
WHERE i.status = 'pending'
AND i.due_date <= CURRENT_DATE
ORDER BY i.due_date ASC;

-- Supporting Index:
CREATE INDEX idx_inst_billing ON installments(due_date, user_id)
WHERE status = 'pending';
-- Partial index: skips paid/waived rows. Estimated selectivity: ~2-5% of total rows.
-- Expected execution: <50ms for 100K active installments.
### Query Pattern 2: User Credit Available Check (per order, real-time)
-- Query: Check if user has sufficient available credit before order approval
SELECT credit_limit, available_credit, status, risk_level
FROM users
WHERE id = $1 AND deleted_at IS NULL;

-- Supporting Index:
CREATE INDEX idx_users_credit_check ON users(id)
INCLUDE (credit_limit, available_credit, status, risk_level)
WHERE deleted_at IS NULL;
-- Covering index: all needed columns in index, zero heap fetch. <1ms.
### Query Pattern 3: Active Loans for User Dashboard
-- Query: User's loan summary for app home screen
SELECT l.id, l.loan_number, l.total_outstanding, l.status, l.expected_end_date,
COUNT(i.id) FILTER (WHERE i.status='pending') as pending_count
FROM loans l
LEFT JOIN installments i ON i.loan_id = l.id
WHERE l.user_id = $1 AND l.status IN ('active','partially_paid')
GROUP BY l.id;

-- Supporting Indexes:
CREATE INDEX idx_loans_user_active ON loans(user_id)
INCLUDE (loan_number, total_outstanding, status, expected_end_date)
WHERE status IN ('active','partially_paid');
CREATE INDEX idx_inst_loan_pending ON installments(loan_id)
WHERE status = 'pending';
### Query Pattern 4: Order State Machine Transition
-- Query: Get current state before transition (optimistic locking)
SELECT id, status, version FROM orders WHERE uuid = $1 FOR UPDATE;

CREATE UNIQUE INDEX idx_orders_uuid ON orders(uuid);

-- Query: All orders in a state requiring action (purchasing queue)
SELECT id, user_id, merchant_id, product_snapshot
FROM orders WHERE status = 'vcn_issued' ORDER BY created_at ASC LIMIT 50;

CREATE INDEX idx_orders_vcn_issued ON orders(created_at ASC)
WHERE status = 'vcn_issued';
### Query Pattern 5: Fraud Velocity Check (per request, real-time)
-- Query: Count orders by user in last 24 hours (velocity check)
SELECT COUNT(*) FROM orders
WHERE user_id = $1 AND created_at > NOW() - INTERVAL '24 hours';

CREATE INDEX idx_orders_velocity ON orders(user_id, created_at DESC);

-- Query: Same IP multiple users (synthetic identity signal)
SELECT COUNT(DISTINCT user_id) FROM users
WHERE registration_ip = $1 AND created_at > NOW() - INTERVAL '7 days';

CREATE INDEX idx_users_reg_ip ON users(registration_ip, created_at DESC);
### Query Pattern 6: Admin Order Search
-- Query: Admin searches orders by various filters
SELECT o.*, u.email, u.phone FROM orders o
JOIN users u ON u.id = o.user_id
WHERE o.status = $1 AND o.merchant_id = $2
AND o.created_at BETWEEN $3 AND $4
ORDER BY o.created_at DESC LIMIT 50 OFFSET $5;

CREATE INDEX idx_orders_admin_search ON orders(status, merchant_id, created_at DESC);

-- Query: Text search on order number
CREATE INDEX idx_orders_number_text ON orders(order_number);
## 17.3 Full Index Inventory by Table
## 17.4 Index Maintenance Strategy
-- Monitor index usage (weekly — drop unused indexes)
SELECT schemaname, tablename, indexname,
idx_scan AS times_used,
pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
ORDER BY idx_scan ASC;

-- Rebuild bloated indexes (monthly during low traffic 2-4 AM)
REINDEX INDEX CONCURRENTLY idx_orders_user_status;

-- Auto-vacuum tuning for high-write tables
ALTER TABLE payment_transactions SET (
autovacuum_vacuum_scale_factor = 0.01,   -- Vacuum at 1% dead rows (default 20%)
autovacuum_analyze_scale_factor = 0.005
);

-- Monitor table bloat
SELECT tablename, n_dead_tup, n_live_tup,
round(n_dead_tup::numeric/NULLIF(n_live_tup+n_dead_tup,0)*100,1) AS bloat_pct
FROM pg_stat_user_tables
WHERE n_dead_tup > 10000
ORDER BY bloat_pct DESC;

# 18. Partitioning & Sharding Plan
SahulatKar will grow from ~0 to potentially 5M+ users over its first 3 years. This section defines exactly which tables to partition, when to introduce sharding, and how to migrate data without downtime.
## 18.1 When to Partition vs When to Shard
## 18.2 Declarative Table Partitioning — Full Implementation
### Partitioned Table: orders (Range by created_at, Quarterly)
-- orders table is RANGE partitioned by created_at (quarterly)
-- Quarterly chosen over monthly: fewer partition management overhead while
-- still giving 90%+ query pruning for time-bounded reports

CREATE TABLE orders (
id          BIGSERIAL,
created_at  TIMESTAMP NOT NULL,
... -- all columns as defined in Section 7
PRIMARY KEY (id, created_at)   -- PK must include partition key
) PARTITION BY RANGE (created_at);

-- 2025 Partitions
CREATE TABLE orders_2025_q1 PARTITION OF orders FOR VALUES FROM ('2025-01-01') TO ('2025-04-01');
CREATE TABLE orders_2025_q2 PARTITION OF orders FOR VALUES FROM ('2025-04-01') TO ('2025-07-01');
CREATE TABLE orders_2025_q3 PARTITION OF orders FOR VALUES FROM ('2025-07-01') TO ('2025-10-01');
CREATE TABLE orders_2025_q4 PARTITION OF orders FOR VALUES FROM ('2025-10-01') TO ('2026-01-01');
-- 2026 Partitions (created by pg_cron 2 weeks before quarter end)
CREATE TABLE orders_2026_q1 PARTITION OF orders FOR VALUES FROM ('2026-01-01') TO ('2026-04-01');

-- DEFAULT partition catches data outside defined ranges (prevents insert errors)
CREATE TABLE orders_default PARTITION OF orders DEFAULT;

-- Each partition inherits the parent's indexes automatically
-- Local indexes per partition for additional performance:
CREATE INDEX idx_orders_2025q1_status ON orders_2025_q1(status, user_id);
### Auto-Create Partitions via pg_cron
CREATE OR REPLACE FUNCTION create_quarterly_partition(
p_table_name TEXT,
p_quarter_start DATE
) RETURNS void AS $$
DECLARE
v_partition_name TEXT;
v_quarter_end    DATE;
BEGIN
v_quarter_end := p_quarter_start + INTERVAL '3 months';
v_partition_name := p_table_name || '_'
|| TO_CHAR(p_quarter_start, 'YYYY') || '_q'
|| TO_CHAR(p_quarter_start, 'Q');

EXECUTE format(
'CREATE TABLE IF NOT EXISTS %I PARTITION OF %I
FOR VALUES FROM (%L) TO (%L)',
v_partition_name, p_table_name, p_quarter_start, v_quarter_end
);
RAISE NOTICE 'Created partition: %', v_partition_name;
END;
$$ LANGUAGE plpgsql;

-- Schedule: 2 weeks before each quarter end, create next quarter's partition
SELECT cron.schedule(
'create-orders-partition-q2',
'0 6 15 3 *',   -- March 15th
$$ SELECT create_quarterly_partition('orders', '2026-04-01'); $$
);
### Partitioned Tables — Complete List
## 18.3 Read Replica Architecture
Deploy read replicas from Year 1 Quarter 1. Even at 1K users the admin dashboard, reporting, and fraud monitoring create significant read load that should not compete with OLTP writes on the primary.
┌────────────────────────────────────────────────────────────────┐
│                   POSTGRESQL CLUSTER (Year 1)                  │
├────────────────────────────────────────────────────────────────┤
│  PRIMARY (r6g.xlarge – 32GB RAM, 4 vCPU, 500GB gp3 SSD)      │
│  Handles: All writes (orders, payments, KYC, fraud alerts)    │
│  Connection Pool: PgBouncer (200 connections max)              │
│                         │                                      │
│           Streaming Replication (WAL)                          │
│           Replication lag target: <1 second                    │
│                ┌────────┴────────┐                             │
│         REPLICA 1            REPLICA 2                        │
│      (r6g.large 16GB)     (r6g.large 16GB)                    │
│      User-facing reads    Admin & Reports                      │
│      App API selects      Admin dashboard                      │
│      Product/order GET    Analytics queries                    │
│      Credit limit checks  Reconciliation runs                  │
└────────────────────────────────────────────────────────────────┘

-- Connection string routing at application layer:
-- PRIMARY:   write operations, SELECT FOR UPDATE
-- REPLICA 1: all GET API responses (user-facing)
-- REPLICA 2: admin panel, scheduled jobs, reporting
## 18.4 Horizontal Sharding — Future State (Year 3+)
Horizontal sharding is NOT recommended until the user base exceeds 1 million active users OR the primary database exceeds 2TB. At that scale, evaluate Citus (PostgreSQL extension for distributed tables) before migrating to custom shard routing.
-- Sharding key: user_id (all user data co-located on same shard)
-- Shard routing table (maintained by application / proxy layer):

CREATE TABLE shard_routing (
user_id_start   BIGINT NOT NULL,
user_id_end     BIGINT NOT NULL,
shard_name      VARCHAR(50) NOT NULL,  -- 'shard_01','shard_02'
shard_host      VARCHAR(255) NOT NULL,
is_active       BOOLEAN NOT NULL DEFAULT TRUE,
PRIMARY KEY (user_id_start, user_id_end)
);

-- Year 3 example distribution (5M users, 4 shards):
-- Shard 1: user_id 1 - 1,250,000        → DB host pk-shard-01.internal
-- Shard 2: user_id 1,250,001 - 2,500,000 → DB host pk-shard-02.internal
-- Shard 3: user_id 2,500,001 - 3,750,000 → DB host pk-shard-03.internal
-- Shard 4: user_id 3,750,001 - 5,000,000 → DB host pk-shard-04.internal

-- Cross-shard entities (NOT sharded — shared across all shards):
-- merchants, couriers, ledger_accounts, system_settings, feature_flags
-- These live in a dedicated 'shared' database read by all application pods

# 19. Database Security Architecture
SahulatKar handles CNIC numbers, bank account details, virtual card data, and financial contracts — all classified as PII and financial data under Pakistan's Prevention of Electronic Crimes Act (PECA) 2016 and SECP regulations. Defense-in-depth security is mandatory.
## 19.1 Database User & Privilege Matrix
-- Create application user with restricted privileges
CREATE USER sk_app WITH PASSWORD '${VAULT_PG_PASSWORD}' CONNECTION LIMIT 50;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO sk_app;
REVOKE DELETE ON users, loans, murabaha_contracts, wakalah_agreements,
payment_transactions, journal_entries FROM sk_app;

-- Read-only reporting user with PII masking view
CREATE USER sk_reporting WITH PASSWORD '${VAULT_PG_REPORTING_PASSWORD}' CONNECTION LIMIT 10;

-- PII-masked view for reporting (no raw CNIC, no bank account)
CREATE VIEW reporting.users_masked AS
SELECT id, uuid, status, kyc_status, risk_level,
'user_' || id || '@masked.com' AS email,  -- Masked email
'+9230XXXXXXX'                AS phone,   -- Masked phone
NULL                          AS cnic_encrypted,
city, province, mobile_operator,
credit_limit, available_credit,
created_at
FROM users;
GRANT SELECT ON reporting.users_masked TO sk_reporting;
## 19.2 Row-Level Security (RLS)
-- Users can only see their own data (enforced at DB layer)
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY orders_user_isolation ON orders
AS PERMISSIVE FOR SELECT
TO sk_app
USING (user_id = current_setting('app.current_user_id')::BIGINT);

-- Admin bypass (admins see all)
CREATE POLICY orders_admin_bypass ON orders
AS PERMISSIVE FOR ALL
TO sk_admin_api
USING (TRUE);

-- Set context per request (application must set this before queries)
-- In Node.js: await pool.query('SET app.current_user_id = $1', [userId]);

-- Apply RLS to all sensitive tables:
-- loans, installments, murabaha_contracts, wakalah_agreements
-- user_kyc_verifications, user_payment_methods, user_bank_accounts
-- payment_transactions, support_tickets, user_devices
## 19.3 Column-Level Encryption (pgcrypto)
-- Enable pgcrypto extension
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Fields requiring AES-256 encryption (stored as BYTEA):
-- users.cnic_encrypted
-- user_payment_methods.iban_encrypted
-- user_payment_methods.wallet_number (if sensitive)
-- virtual_cards.card_number_encrypted (if stored — prefer tokenization)
-- admin_users.mfa_secret_encrypted
-- couriers.api_key_encrypted
-- api_keys metadata

-- Write encrypted value (application layer, not DB function in production):
-- In application: cipher = AES_256_GCM_encrypt(plaintext, KEY_FROM_VAULT)
-- INSERT INTO users (cnic_encrypted) VALUES ($cipher_bytes)

-- DB-layer encryption (dev/testing only — key in DB is insecure for prod):
UPDATE users
SET cnic_encrypted = pgp_sym_encrypt(cnic_plaintext, current_setting('app.enc_key'))
WHERE id = $1;

-- Read:
SELECT pgp_sym_decrypt(cnic_encrypted, current_setting('app.enc_key')) AS cnic
FROM users WHERE id = $1;

-- Key Management:
-- Production: AWS KMS Customer Managed Key (CMK)
-- Encryption: Application fetches key from KMS, encrypts in memory, stores BYTEA
-- Key Rotation: Annual or on suspected compromise; KMS handles re-encryption
-- Never store plaintext keys in DB, .env files, or application config
## 19.4 Transport Layer Security
## 19.5 SQL Injection Prevention
// ✅ CORRECT: Parameterized query (TypeORM / Prisma / node-postgres)
const result = await db.query(
'SELECT * FROM orders WHERE user_id = $1 AND status = $2',
[userId, status]
);

// ❌ WRONG: String interpolation (SQL injection vector)
const result = await db.query(
`SELECT * FROM orders WHERE user_id = ${userId}` // NEVER DO THIS
);

// ORM usage (Prisma example) — all queries parameterized by default
const orders = await prisma.orders.findMany({
where: { userId: userId, status: 'active' }
});

-- Database-level: restrict pg_stat_statements to admin users only
REVOKE ALL ON pg_stat_statements FROM PUBLIC;
GRANT SELECT ON pg_stat_statements TO sk_admin_api;

# 20. Backup & Disaster Recovery Strategy
SahulatKar's backup strategy must satisfy two competing requirements: (1) regulatory 7-year retention of all financial records, and (2) practical recovery objectives that minimize business disruption in case of data loss or system failure.
## 20.1 Recovery Objectives
## 20.2 Backup Schedule
┌──────────────────────────────────────────────────────────────────┐
│  BACKUP TYPE          FREQUENCY    RETENTION    STORAGE          │
├──────────────────────────────────────────────────────────────────┤
│  WAL Archival         Continuous   7 days       S3 Standard     │
│  (Point-in-Time)      (streaming)  (PITR)       Encrypted CMK   │
│                                                                  │
│  Automated Snapshot   Daily 2AM    30 days      AWS RDS EBS     │
│  (AWS RDS managed)    PKT                       Auto-encrypted  │
│                                                                  │
│  Weekly Full Dump     Sunday 3AM   90 days      S3 Standard-IA  │
│  (pg_dump + gzip)     PKT          (warm)       Cross-region    │
│                                                                  │
│  Monthly Compliance   1st of month 7 years      S3 Glacier      │
│  Archive (financial)  4AM PKT      (cold)       Deep Archive    │
└──────────────────────────────────────────────────────────────────┘
## 20.3 Automated Backup Scripts
#!/bin/bash
# /scripts/backup_weekly.sh — runs every Sunday 3AM PKT via cron

DB_HOST=${RDS_HOST}
DB_NAME='sahulatkar_prod'
S3_BUCKET='sahulatkar-db-backups'
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="full_backup_${DATE}.dump.gz"

# Full backup with parallel compression
pg_dump -h $DB_HOST -U sk_migrations -Fc -Z6 $DB_NAME | \
gzip > /tmp/$BACKUP_FILE

# Upload to S3 with server-side encryption
aws s3 cp /tmp/$BACKUP_FILE \
s3://${S3_BUCKET}/weekly/${BACKUP_FILE} \
--sse aws:kms \
--sse-kms-key-id ${KMS_KEY_ARN} \
--storage-class STANDARD_IA

# Verify upload
aws s3 ls s3://${S3_BUCKET}/weekly/${BACKUP_FILE} || exit 1

# Alert on success/failure
curl -X POST ${SLACK_WEBHOOK} \
-d '{"text":"Weekly DB backup completed: '${BACKUP_FILE}'"}'

# Cleanup local temp file
rm /tmp/$BACKUP_FILE
## 20.4 Restore Procedures
-- SCENARIO: Point-in-Time Restore (accidental delete, table corruption)
-- Step 1: Identify target restore time
--   Find last clean transaction before incident using audit_trails
SELECT MAX(changed_at) FROM audit_trails
WHERE table_name = 'orders' AND changed_at < '2025-06-01 14:30:00';

-- Step 2: Via AWS RDS Console / CLI
aws rds restore-db-instance-to-point-in-time \
--source-db-instance-identifier sahulatkar-prod \
--target-db-instance-identifier sahulatkar-restore-temp \
--restore-time 2025-06-01T14:29:00Z

-- Step 3: Extract affected table from restored instance
pg_dump -h sahulatkar-restore-temp.rds.amazonaws.com \
-U sk_migrations -t orders --data-only \
sahulatkar_prod > orders_recovered.sql

-- Step 4: Restore to production (with validation)
-- Apply with BEGIN/COMMIT for safety
BEGIN;
-- Restore deleted rows only
INSERT INTO orders SELECT * FROM orders_recovered WHERE id NOT IN (SELECT id FROM orders);
-- Verify count
SELECT COUNT(*) FROM orders; -- Compare with expected
COMMIT; -- or ROLLBACK if count is wrong
## 20.5 Backup Testing & DR Drills

# 21. Performance Optimization Strategy
Performance optimization is an ongoing discipline, not a one-time task. This section defines the baseline PostgreSQL configuration, caching strategy, connection pooling, query optimization patterns, and materialized view designs for SahulatKar's operational workload.
## 21.1 PostgreSQL Configuration (postgresql.conf)
# ── Memory Settings (for r6g.xlarge: 32GB RAM) ──────────────────
shared_buffers = 8GB                  # 25% of RAM — PostgreSQL's buffer cache
effective_cache_size = 24GB           # 75% of RAM — hint for query planner
work_mem = 64MB                       # Per-sort/hash operation; 200 connections = 12.8GB max
maintenance_work_mem = 2GB            # For VACUUM, CREATE INDEX, ALTER TABLE

# ── WAL & Checkpoints ─────────────────────────────────────────────
wal_level = replica                   # Enable streaming replication
max_wal_size = 4GB
min_wal_size = 1GB
checkpoint_completion_target = 0.9    # Smooth checkpoint writes over 90% of interval
wal_buffers = 64MB
synchronous_commit = on               # Financial safety: ensure WAL flushed before ack

# ── Query Planner ─────────────────────────────────────────────────
random_page_cost = 1.1                # SSD storage: reduce vs HDD default of 4.0
effective_io_concurrency = 200        # SSD can handle 200 concurrent I/O
default_statistics_target = 200       # Better query plans (default 100)

# ── Connection Handling ───────────────────────────────────────────
max_connections = 200                 # PgBouncer sits in front; app connects to pooler

# ── Parallel Query ─────────────────────────────────────────────────
max_parallel_workers_per_gather = 2   # Use 2 cores for parallel seq scans
max_parallel_workers = 4

# ── Logging (Slow Query Detection) ────────────────────────────────
log_min_duration_statement = 100      # Log all queries > 100ms
log_checkpoints = on
log_lock_waits = on
log_temp_files = 10MB                 # Log queries spilling to disk

# ── Extensions ────────────────────────────────────────────────────
shared_preload_libraries = 'pg_stat_statements,pg_cron,timescaledb'
pg_stat_statements.max = 10000
pg_stat_statements.track = all
## 21.2 Connection Pooling (PgBouncer)
# pgbouncer.ini
[databases]
sahulatkar_prod = host=rds-primary.internal port=5432 dbname=sahulatkar_prod
sahulatkar_readonly = host=rds-replica1.internal port=5432 dbname=sahulatkar_prod

[pgbouncer]
listen_port = 6432
listen_addr = *
auth_type = scram-sha-256
pool_mode = transaction          # Transaction pooling: connection returned after each txn
max_client_conn = 2000           # Max total client connections
default_pool_size = 25           # Connections per database-user pair to actual PG
reserve_pool_size = 5            # Emergency connections
reserve_pool_timeout = 5
server_idle_timeout = 600        # Close idle server connections after 10 min
client_idle_timeout = 300
max_db_connections = 180         # Leave headroom for direct admin access (max_connections=200)
server_reset_query = DISCARD ALL # Reset session state between clients
server_tls_sslmode = require

# Connection sizing formula:
# App instances: 10 pods × 5 connections each = 50 app connections
# Admin panel: 3 instances × 5 = 15
# Workers: 20 pods × 3 = 60
# Reporting: 5 × 2 = 10
# Total app-layer connections: ~135 (well within pool_size × databases)
## 21.3 Redis Caching Strategy
## 21.4 Materialized Views for Reporting
-- MV 1: Daily revenue summary (admin dashboard KPIs)
CREATE MATERIALIZED VIEW mv_daily_revenue AS
SELECT
DATE(o.created_at AT TIME ZONE 'Asia/Karachi') AS report_date,
COUNT(DISTINCT o.id)               AS orders_completed,
SUM(o.product_cost)                AS gmv,
SUM(o.platform_profit)             AS gross_profit,
AVG(o.total_amount)                AS avg_order_value,
COUNT(DISTINCT o.user_id)          AS unique_buyers
FROM orders o
WHERE o.status = 'completed'
GROUP BY DATE(o.created_at AT TIME ZONE 'Asia/Karachi');

CREATE UNIQUE INDEX ON mv_daily_revenue(report_date);

-- Refresh nightly at 1 AM (pg_cron)
SELECT cron.schedule('refresh-daily-revenue', '0 1 * * *',
'REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_revenue');

-- MV 2: Portfolio health (risk/finance team)
CREATE MATERIALIZED VIEW mv_loan_portfolio AS
SELECT
l.status,
COUNT(*)                           AS loan_count,
SUM(l.total_outstanding)           AS total_outstanding,
SUM(l.late_fee_total)              AS total_late_fees,
AVG(l.total_outstanding)           AS avg_outstanding,
COUNT(*) FILTER (WHERE l.status='defaulted') AS defaults
FROM loans l
GROUP BY l.status;

-- MV 3: Merchant performance (partnership team)
CREATE MATERIALIZED VIEW mv_merchant_performance AS
SELECT
m.id, m.name, m.domain,
COUNT(o.id)                        AS total_orders,
AVG(CASE WHEN pe.status='succeeded' THEN 1 ELSE 0 END) AS checkout_success_rate,
AVG(pe.duration_ms)                AS avg_checkout_ms,
SUM(o.product_cost)                AS total_gmv
FROM merchants m
LEFT JOIN orders o ON o.merchant_id = m.id
LEFT JOIN purchase_executions pe ON pe.order_id = o.id AND pe.attempt_number = 1
GROUP BY m.id, m.name, m.domain;
## 21.5 Slow Query Identification & Resolution Process
-- Step 1: Find top 20 slowest queries (run weekly)
SELECT
LEFT(query, 100) AS query_preview,
ROUND(mean_exec_time::numeric, 2) AS avg_ms,
calls,
ROUND((total_exec_time / 1000)::numeric, 0) AS total_seconds,
ROUND(rows::numeric / NULLIF(calls,0), 1) AS avg_rows
FROM pg_stat_statements
WHERE mean_exec_time > 50
ORDER BY mean_exec_time DESC
LIMIT 20;

-- Step 2: Analyze query plan for worst offenders
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT i.*, u.phone FROM installments i
JOIN users u ON u.id = i.user_id
WHERE i.status = 'pending' AND i.due_date <= CURRENT_DATE;

-- Step 3: Look for these warning signs in EXPLAIN output:
-- 'Seq Scan' on large table → add/fix index
-- 'Hash Join' on large tables → consider index-based nested loop
-- 'rows=X (actual=Y)' with large difference → run ANALYZE to update statistics
-- 'Buffers: shared read=X' with X > 10000 → too many I/O blocks, index needed
-- 'Sort Method: external merge' → work_mem too low or add index for ORDER BY

-- Step 4: After fix, reset stats and verify improvement
SELECT pg_stat_statements_reset();  -- Reset after adding index
-- Wait 24 hours, re-run Step 1 to verify improvement

# 22. Database Migration Strategy
Schema evolution is inevitable. SahulatKar will ship dozens of migrations per quarter as new payment methods, merchants, fraud rules, and product features are added. The migration strategy must guarantee zero-downtime deployments, reversibility, and audit trail.
## 22.1 Toolchain Selection
Recommended: Flyway Community Edition (Java-based, version-controlled, checksum-validated). Alternative: Atlas (Go-based, schema-as-code, supports declarative migrations). Avoid Liquibase XML for this project — SQL migrations are more readable for a DB-heavy platform.
## 22.2 Migration File Structure
migrations/
├── V001__create_initial_schema.sql
├── V002__create_users_table.sql
├── V003__create_orders_table.sql
├── V004__create_loans_and_installments.sql
├── V005__create_murabaha_wakalah_contracts.sql
├── V006__create_audit_trail_system.sql
├── V007__create_fraud_detection_tables.sql
├── V008__create_payment_tables.sql
├── V009__create_delivery_tables.sql
├── V010__create_accounting_tables.sql
├── V011__create_admin_rbac.sql
├── V012__create_marketing_tables.sql
├── V013__create_support_tables.sql
├── V014__create_system_integration_tables.sql
├── V015__seed_reference_data.sql
├── V016__seed_pakistan_cities_postal_codes.sql
├── V017__seed_shariah_approved_categories.sql
├── V018__add_raast_payment_method.sql  ← feature migration
├── V019__add_installment_rescheduling.sql
├── R__refresh_materialized_views.sql   ← repeatable migration
seeds/
├── S001__ledger_accounts.sql
├── S002__couriers.sql
├── S003__system_settings.sql
tests/
├── V001__verify_schema.sql
├── V018__verify_raast.sql
## 22.3 Zero-Downtime Migration Patterns
### Pattern A: Add New Non-Nullable Column
-- Naive approach (causes table lock on large tables — AVOID):
-- ALTER TABLE users ADD COLUMN new_field VARCHAR(100) NOT NULL DEFAULT 'x';

-- Zero-downtime 3-step process:

-- Migration V020: Step 1 — Add as nullable (fast, no lock on data)
ALTER TABLE users ADD COLUMN preferred_currency CHAR(3);
ALTER TABLE users ADD CONSTRAINT chk_currency
CHECK (preferred_currency IN ('PKR', 'USD') OR preferred_currency IS NULL);

-- Migration V021: Step 2 — Backfill in batches (no table lock)
DO $$ DECLARE batch_size INT := 10000; last_id BIGINT := 0;
BEGIN
LOOP
UPDATE users SET preferred_currency = 'PKR'
WHERE id > last_id AND preferred_currency IS NULL
LIMIT batch_size RETURNING id INTO last_id;
EXIT WHEN NOT FOUND;
PERFORM pg_sleep(0.1); -- Rate limit: avoid I/O saturation
END LOOP;
END $$;

-- Migration V022: Step 3 — Set NOT NULL (fast if no nulls remain)
ALTER TABLE users ALTER COLUMN preferred_currency SET NOT NULL;
ALTER TABLE users ALTER COLUMN preferred_currency SET DEFAULT 'PKR';
### Pattern B: Rename a Column
-- Naive: ALTER TABLE users RENAME COLUMN phone TO mobile_number;
-- Problem: Breaks application code instantly if done atomically

-- Zero-downtime 5-step rename:
-- V023: Add new column
ALTER TABLE users ADD COLUMN mobile_number VARCHAR(20);

-- V024: Create trigger to dual-write (keep both in sync during transition)
CREATE TRIGGER trg_sync_mobile_number
BEFORE INSERT OR UPDATE ON users FOR EACH ROW
EXECUTE FUNCTION fn_sync_phone_to_mobile();

-- V025: Backfill new column from old
UPDATE users SET mobile_number = phone WHERE mobile_number IS NULL;

-- V026: Deploy app version that reads from new column only
-- (Deploy happens here, between migrations)

-- V027: Drop old column and trigger
DROP TRIGGER trg_sync_mobile_number ON users;
ALTER TABLE users DROP COLUMN phone;
### Pattern C: Add Index on Large Table
-- Standard CREATE INDEX acquires ShareLock — blocks all writes for minutes!
-- ALWAYS use CONCURRENTLY for production tables > 100K rows:

-- Run OUTSIDE of a transaction block (CONCURRENTLY doesn't support transactions)
CREATE INDEX CONCURRENTLY idx_orders_merchant_date
ON orders(merchant_id, created_at DESC);

-- Monitor progress:
SELECT phase, blocks_done, blocks_total,
ROUND(100.0 * blocks_done / NULLIF(blocks_total,0), 1) AS pct_done
FROM pg_stat_progress_create_index
WHERE relid = 'orders'::regclass;

-- If failed midway, clean up invalid index before retrying:
DROP INDEX CONCURRENTLY IF EXISTS idx_orders_merchant_date;
## 22.4 Migration Governance

# 23. Pakistan-Specific Database Considerations
SahulatKar is purpose-built for Pakistan's market. This section documents all database design decisions driven by Pakistan-specific requirements: regulatory, demographic, geographic, linguistic, payment infrastructure, and cultural considerations.
## 23.1 CNIC Data Model & Validation
-- Pakistan CNIC format: DDDDD-DDDDDDD-D (5-7-1 digits)
-- Digits 1-5: Division code
-- Digits 6-12: Unique serial within division
-- Digit 13: Gender indicator (odd=male, even=female) + check digit

-- Storage: Encrypted BYTEA + SHA-256 hash for uniqueness check
ALTER TABLE users ADD COLUMN cnic_encrypted BYTEA;           -- AES-256
ALTER TABLE users ADD COLUMN cnic_hash VARCHAR(64);           -- SHA-256 for dedup
ALTER TABLE users ADD COLUMN cnic_verified_via VARCHAR(20);   -- 'nadra_api','manual'
ALTER TABLE users ADD COLUMN cnic_expiry_date DATE;           -- CNICs expire

-- Uniqueness enforced on hash (not encrypted value)
CREATE UNIQUE INDEX idx_users_cnic_hash ON users(cnic_hash) WHERE deleted_at IS NULL;

-- CNIC extraction function (demographic analytics, no PII exposure)
CREATE OR REPLACE FUNCTION cnic_to_gender(cnic_plain TEXT) RETURNS CHAR(1) AS $$
BEGIN
-- Digit 13 odd = Male, even = Female
RETURN CASE WHEN (RIGHT(cnic_plain,1)::INT % 2) = 1 THEN 'M' ELSE 'F' END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Province lookup from CNIC division code
CREATE TABLE cnic_division_codes (
division_code   CHAR(5) PRIMARY KEY,
province        VARCHAR(50),
division_name   VARCHAR(100)
);
-- Populated with NADRA division codes (614 total divisions in Pakistan)
## 23.2 Pakistan Postal System & City Mapping
CREATE TABLE pakistan_postal_codes (
postal_code     VARCHAR(10) PRIMARY KEY,
city            VARCHAR(100) NOT NULL,
district        VARCHAR(100),
division        VARCHAR(100),
province        VARCHAR(50) NOT NULL
CHECK (province IN ('Sindh','Punjab','KPK',
'Balochistan','Gilgit-Baltistan','AJK','ICT')),
is_serviceable  BOOLEAN NOT NULL DEFAULT FALSE,  -- SahulatKar coverage
courier_ids     INTEGER[],                       -- Couriers serving this area
latitude        DECIMAL(10,8),
longitude       DECIMAL(11,8)
);
-- Seed data: ~11,000 Pakistan postal codes from Pakistan Post data

-- Major cities coverage table
CREATE TABLE pakistan_cities (
id              SERIAL PRIMARY KEY,
name            VARCHAR(100) NOT NULL,
name_urdu       VARCHAR(100),            -- Urdu name (Lahore = لاہور)
province        VARCHAR(50) NOT NULL,
is_metro        BOOLEAN NOT NULL DEFAULT FALSE,  -- Karachi, Lahore, Islamabad
population      INTEGER,
has_courier_hub BOOLEAN NOT NULL DEFAULT FALSE,
launch_phase    SMALLINT,               -- 1=launch, 2=phase2, 3=phase3
latitude        DECIMAL(10,8),
longitude       DECIMAL(11,8)
);
## 23.3 Pakistani Mobile Operator & Payment Method Detection
-- Mobile operator prefix table (for routing to JazzCash vs EasyPaisa)
CREATE TABLE pk_mobile_prefixes (
prefix          VARCHAR(7) PRIMARY KEY,   -- '+923XX'
operator        VARCHAR(20) NOT NULL
CHECK (operator IN ('jazz','telenor','zong','ufone','warid')),
supports_jazzcash BOOLEAN NOT NULL DEFAULT FALSE,
supports_easypaisa BOOLEAN NOT NULL DEFAULT FALSE
);
-- Seed: Jazz (+923001-3009, +923401-3459, +923451-3479, +923481-3499)
--       Telenor (+923411-3439, +923361-3369, +923300-3009)
--       (Full PMDA prefix list — 200+ prefixes)

-- Function: determine which mobile wallet to offer
CREATE OR REPLACE FUNCTION get_wallet_options(phone TEXT)
RETURNS TEXT[] AS $$
DECLARE
v_prefix TEXT := LEFT(phone, 7);
v_options TEXT[] := '{}';
BEGIN
SELECT ARRAY_REMOVE(ARRAY[
CASE WHEN supports_jazzcash THEN 'jazzcash' END,
CASE WHEN supports_easypaisa THEN 'easypaisa' END
], NULL) INTO v_options
FROM pk_mobile_prefixes WHERE prefix = v_prefix;
RETURN COALESCE(v_options, ARRAY['bank_account']);
END;
$$ LANGUAGE plpgsql;
## 23.4 Islamic Calendar & Shariah Date Awareness
-- Hijri calendar table for Ramadan-aware features
-- (Ramadan financing promotions, Eid payment grace periods)
CREATE TABLE islamic_calendar (
gregorian_date  DATE PRIMARY KEY,
hijri_year      SMALLINT NOT NULL,
hijri_month     SMALLINT NOT NULL CHECK (hijri_month BETWEEN 1 AND 12),
hijri_day       SMALLINT NOT NULL CHECK (hijri_day BETWEEN 1 AND 30),
month_name_en   VARCHAR(20),            -- 'Ramadan', 'Dhul Hijja'
month_name_ur   VARCHAR(20),            -- 'رمضان'
is_ramadan      BOOLEAN NOT NULL DEFAULT FALSE,
is_eid_ul_fitr  BOOLEAN NOT NULL DEFAULT FALSE,
is_eid_ul_adha  BOOLEAN NOT NULL DEFAULT FALSE,
is_public_holiday BOOLEAN NOT NULL DEFAULT FALSE
);
-- Seed: 5-year Hijri-Gregorian calendar from verified Islamic sources

-- Business rule: Don't schedule payment retries on Eid holidays
CREATE OR REPLACE FUNCTION is_payment_holiday(check_date DATE)
RETURNS BOOLEAN AS $$
SELECT COALESCE(
(SELECT is_public_holiday OR is_eid_ul_fitr OR is_eid_ul_adha
FROM islamic_calendar WHERE gregorian_date = check_date),
FALSE
);
$$ LANGUAGE SQL;
## 23.5 Urdu Language Support
-- PostgreSQL collation for Urdu text
-- Urdu uses Arabic script; PostgreSQL supports UTF-8 natively
CREATE COLLATION urdu_collation (provider = icu, locale = 'ur-PK');

-- Urdu full-text search configuration
-- Note: PostgreSQL does not have a native Urdu text search dictionary
-- Strategy: Use 'simple' dictionary (no stemming) for Urdu tokens
CREATE TEXT SEARCH CONFIGURATION urdu (COPY = simple);

-- Product search supporting both English and Urdu queries
ALTER TABLE products ADD COLUMN search_vector_urdu TSVECTOR;

CREATE TRIGGER trg_products_search_urdu BEFORE INSERT OR UPDATE ON products
FOR EACH ROW EXECUTE FUNCTION
tsvector_update_trigger(search_vector_urdu, 'pg_catalog.simple', title_urdu);

-- Combined search (English OR Urdu match)
SELECT * FROM products
WHERE search_vector @@ to_tsquery('english', $1)
OR search_vector_urdu @@ to_tsquery('simple', $1)
ORDER BY
ts_rank(search_vector, to_tsquery('english', $1)) +
ts_rank(search_vector_urdu, to_tsquery('simple', $1)) DESC
LIMIT 20;
## 23.6 SECP & SBP Regulatory Data Requirements

# 24. Comprehensive Audit Logging & Compliance Trail
Audit logging is non-negotiable for a financial platform operating under SECP oversight. Every data change, admin action, API call, and authentication event must be captured, tamper-evident, and queryable for at least 7 years. This section defines the complete audit architecture.
## 24.1 Audit Coverage Matrix
## 24.2 Audit Trigger Deployment
-- Deploy audit trigger to ALL sensitive tables
-- (audit trigger function fn_log_audit defined in Section 15.1)

DO $$ DECLARE
t TEXT;
sensitive_tables TEXT[] := ARRAY[
'users', 'loans', 'installments', 'payment_transactions',
'murabaha_contracts', 'wakalah_agreements', 'virtual_cards',
'credit_applications', 'credit_limit_history', 'risk_assessments',
'fraud_alerts', 'user_kyc_verifications', 'user_payment_methods',
'user_bank_accounts', 'orders', 'chargebacks', 'refunds',
'late_fee_charity_allocations', 'journal_entries', 'settlements',
'admin_users', 'roles', 'permissions', 'role_permissions',
'system_settings', 'feature_flags', 'api_keys',
'promotional_codes', 'user_consent_records', 'data_deletion_requests'
];
BEGIN
FOREACH t IN ARRAY sensitive_tables LOOP
EXECUTE format(
'CREATE TRIGGER trg_%s_audit
AFTER INSERT OR UPDATE OR DELETE ON %I
FOR EACH ROW EXECUTE FUNCTION fn_log_audit()',
t, t
);
RAISE NOTICE 'Audit trigger created for: %', t;
END LOOP;
END $$;
## 24.3 Application-Level Context Setting
// Node.js middleware: set audit context before every DB operation
// This populates the pg session variables used by fn_log_audit()

async function setAuditContext(pool, req) {
const actorType = req.adminUser ? 'admin' : req.user ? 'customer' : 'system';
const actorId = (req.adminUser?.id || req.user?.id || 0).toString();
const ip = req.headers['x-forwarded-for'] || req.socket.remoteAddress;
const requestId = req.headers['x-request-id'] || crypto.randomUUID();

await pool.query(`
SELECT
set_config('app.actor_type', $1, true),
set_config('app.actor_id', $2, true),
set_config('app.ip_address', $3, true),
set_config('app.request_id', $4, true),
set_config('app.current_user_id', $2, true)`,
[actorType, actorId, ip, requestId]
);
}

// Usage: call before any write operation
await setAuditContext(pool, req);
await pool.query('UPDATE users SET status = $1 WHERE id = $2', ['suspended', userId]);
// audit_trails now has: actor_type='admin', actor_id=adminId, ip, request_id
## 24.4 Audit Query Examples for Compliance
-- 1. Full account change history for a specific user (Regulator request)
SELECT a.changed_at, a.operation, a.table_name,
a.actor_type, a.actor_id,
a.old_values, a.new_values, a.change_reason
FROM audit_trails a
WHERE a.table_name IN ('users','loans','credit_applications','murabaha_contracts')
AND (a.old_values->>'user_id')::BIGINT = 12345
OR a.record_id = 12345
ORDER BY a.changed_at DESC;

-- 2. All credit limit increases in last quarter (Risk Committee review)
SELECT a.changed_at,
(a.old_values->>'credit_limit')::DECIMAL AS old_limit,
(a.new_values->>'credit_limit')::DECIMAL AS new_limit,
a.actor_type, a.actor_id, a.change_reason
FROM audit_trails a
WHERE a.table_name = 'users'
AND a.operation = 'UPDATE'
AND (a.old_values->>'credit_limit')::DECIMAL < (a.new_values->>'credit_limit')::DECIMAL
AND a.changed_at > NOW() - INTERVAL '90 days'
ORDER BY (a.new_values->>'credit_limit')::DECIMAL - (a.old_values->>'credit_limit')::DECIMAL DESC;

-- 3. All admin actions on a specific order (Internal investigation)
SELECT * FROM admin_activity_logs
WHERE target_type = 'order' AND target_id = 67890
ORDER BY created_at;

-- 4. All payment transactions with no gateway confirmation after 1 hour (Ops check)
SELECT pt.id, pt.amount, pt.gateway, pt.status, pt.initiated_at,
u.phone, u.email
FROM payment_transactions pt
JOIN users u ON u.id = pt.user_id
WHERE pt.status = 'pending'
AND pt.initiated_at < NOW() - INTERVAL '1 hour';
## 24.5 Audit Data Archival (7-Year Compliance)
-- Archival process: move audit_trails partitions to S3 as Parquet after 1 year
-- (Run via pg_cron monthly on the 1st, moving partitions from 13+ months ago)

CREATE OR REPLACE FUNCTION archive_old_audit_partition(
partition_name TEXT,
s3_path TEXT
) RETURNS void AS $$
BEGIN
-- Export to S3 using aws_s3 extension (or via application job)
EXECUTE format(
'SELECT aws_s3.query_export_to_s3(
''SELECT * FROM %I'',
aws_commons.create_s3_uri(%L, %L, ''ap-south-1''),
options := ''format csv, header true''
)',
partition_name,
'sahulatkar-audit-archive',
s3_path
);
-- After verified export, detach partition (keep data, remove from active queries)
EXECUTE format('ALTER TABLE audit_trails DETACH PARTITION %I', partition_name);
RAISE NOTICE 'Archived and detached partition: %', partition_name;
END;
$$ LANGUAGE plpgsql;

# 25. Database Sizing & Cost Projections
This section provides data-driven estimates for database storage, compute, and operational costs over SahulatKar's first 5 years of operation, based on conservative growth assumptions: 5,000 users in Year 1, 50,000 in Year 2, 200,000 in Year 3, 750,000 in Year 4, and 2,000,000 in Year 5.
## 25.1 Row Count Projections by Table
## 25.2 Storage Projections
## 25.3 Monthly Infrastructure Cost Projections (AWS)
Cost optimization levers: (1) Reserved Instances (1-year) save 30-40% vs on-demand. Year 1 reserved: ~$730/mo. (2) S3 Intelligent-Tiering automatically moves infrequently accessed data to cheaper tiers. (3) At Year 3+, evaluate Aurora PostgreSQL Serverless v2 for automatic scaling without over-provisioning.
## 25.4 Performance Benchmarks & SLAs
## 25.5 Scalability Decision Thresholds

# Appendix A: Complete Trigger Function Library
## A.1 Universal Update Timestamp Trigger
CREATE OR REPLACE FUNCTION fn_set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
NEW.updated_at := NOW();
RETURN NEW;
END; $$;

-- Apply to all tables with updated_at column:
-- (auto-applied via migration loop)
DO $$ DECLARE t TEXT;
updatable_tables TEXT[] := ARRAY[
'users','orders','loans','installments','products','merchants',
'user_addresses','user_payment_methods','support_tickets',
'webhooks','admin_users','virtual_cards','shipments'
];
BEGIN
FOREACH t IN ARRAY updatable_tables LOOP
EXECUTE format(
'CREATE TRIGGER trg_%s_updated_at
BEFORE UPDATE ON %I FOR EACH ROW
EXECUTE FUNCTION fn_set_updated_at()',
t, t
);
END LOOP;
END $$;
## A.2 Available Credit Recalculation Trigger
-- Automatically recalculate user's available_credit after loan status changes
CREATE OR REPLACE FUNCTION fn_recalculate_available_credit()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
v_outstanding DECIMAL(14,2);
BEGIN
-- Sum all active loan outstanding for this user
SELECT COALESCE(SUM(total_outstanding), 0) INTO v_outstanding
FROM loans
WHERE user_id = COALESCE(NEW.user_id, OLD.user_id)
AND status IN ('active','partially_paid');

-- Update user's credit snapshot
UPDATE users
SET total_outstanding = v_outstanding,
available_credit = GREATEST(credit_limit - v_outstanding, 0)
WHERE id = COALESCE(NEW.user_id, OLD.user_id);

RETURN COALESCE(NEW, OLD);
END; $$;

CREATE TRIGGER trg_loans_credit_update
AFTER INSERT OR UPDATE OF total_outstanding, status ON loans
FOR EACH ROW EXECUTE FUNCTION fn_recalculate_available_credit();
## A.3 Order Number Generation Trigger
-- Generate human-readable order numbers: SAK-2025-0001234
CREATE SEQUENCE seq_order_number START 1000 INCREMENT 1;

CREATE OR REPLACE FUNCTION fn_generate_order_number()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
IF NEW.order_number IS NULL THEN
NEW.order_number := 'SAK-'
|| TO_CHAR(NOW(), 'YYYY') || '-'
|| LPAD(nextval('seq_order_number')::TEXT, 7, '0');
END IF;
RETURN NEW;
END; $$;

CREATE TRIGGER trg_orders_number
BEFORE INSERT ON orders
FOR EACH ROW EXECUTE FUNCTION fn_generate_order_number();

-- Similarly for loans: SAK-LOAN-2025-0001234
-- For contracts: SAK-MUR-2025-0001234 / SAK-WAK-2025-0001234
## A.4 Installment Late Fee Trigger
-- Calculate and apply late fees when installment becomes overdue
CREATE OR REPLACE FUNCTION fn_apply_late_fee()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
v_days_overdue INTEGER;
v_late_fee     DECIMAL(14,2);
v_daily_rate   DECIMAL(8,6) := 0.000274;  -- 0.0274% per day (charity-bound)
BEGIN
-- Only fire when status transitions to 'overdue'
IF OLD.status != 'overdue' AND NEW.status = 'overdue' THEN
v_days_overdue := CURRENT_DATE - NEW.due_date;
v_late_fee := ROUND(NEW.total_amount * v_daily_rate * v_days_overdue, 2);

NEW.days_overdue    := v_days_overdue;
NEW.late_fee_amount := v_late_fee;

-- Create charity allocation record (Shariah: late fee to charity)
INSERT INTO late_fee_charity_allocations(
installment_id, loan_id, late_fee_amount, allocated_at
) VALUES (
NEW.id,
NEW.loan_id,
v_late_fee,
NOW()
);
END IF;
RETURN NEW;
END; $$;

CREATE TRIGGER trg_installment_late_fee
BEFORE UPDATE OF status ON installments
FOR EACH ROW EXECUTE FUNCTION fn_apply_late_fee();

# Appendix B: Operational Runbooks
## B.1 Runbook: Add New Column Safely
# Runbook: Safe Column Addition to Large Table
# Applicable when: table > 1M rows, production environment

# Step 1: Create migration file
# File: V0XX__add_{column}_to_{table}.sql
ALTER TABLE {table} ADD COLUMN {column} {type} NULL;

# Step 2: Deploy migration to staging first
flyway -url=jdbc:postgresql://staging-db/sk -migrate

# Step 3: Run backfill script (batched, run in background on prod)
# Run during off-peak: 2AM - 5AM PKT
DO $$ DECLARE cursor_id BIGINT := 0; batch_size INT := 5000;
BEGIN LOOP
UPDATE {table} SET {column} = {default}
WHERE id > cursor_id AND {column} IS NULL
ORDER BY id LIMIT batch_size
RETURNING MAX(id) INTO cursor_id;
EXIT WHEN cursor_id IS NULL;
PERFORM pg_sleep(0.05);
END LOOP; END $$;

# Step 4: Verify backfill complete
SELECT COUNT(*) FROM {table} WHERE {column} IS NULL;  -- Should be 0

# Step 5: Apply NOT NULL constraint (fast if no nulls)
ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL;
ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT {default};

# Step 6: Validate in production
\d {table}  -- Confirm column definition
## B.2 Runbook: Connection Pool Exhaustion
# Symptoms: 'too many clients' error, requests timing out

# Step 1: Check current connections
SELECT count(*), state, wait_event_type, wait_event
FROM pg_stat_activity
GROUP BY state, wait_event_type, wait_event
ORDER BY count DESC;

# Step 2: Find long-running queries holding connections
SELECT pid, now() - query_start AS duration, query
FROM pg_stat_activity
WHERE state != 'idle'
AND now() - query_start > INTERVAL '30 seconds'
ORDER BY duration DESC;

# Step 3: Kill blocking queries (if safe)
SELECT pg_terminate_backend(pid)  -- Graceful
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
AND state = 'idle in transaction'
AND now() - state_change > INTERVAL '5 minutes';

# Step 4: Check PgBouncer pool status
psql -p 6432 pgbouncer -c 'SHOW POOLS;'
psql -p 6432 pgbouncer -c 'SHOW STATS;'

# Step 5: If persistent, restart PgBouncer (graceful: drains active connections)
sudo systemctl reload pgbouncer
## B.3 Runbook: Partition Creation (Monthly)
# Run on the 15th of each month to create next month's partitions
# Also run via pg_cron automatically — this is the manual procedure

-- Get next month start/end
DO $$ DECLARE
next_month_start DATE := DATE_TRUNC('month', NOW() + INTERVAL '1 month');
next_month_end   DATE := next_month_start + INTERVAL '1 month';
p_name TEXT;
BEGIN
FOREACH p_name IN ARRAY ARRAY[
'audit_trails', 'tracking_events', 'integration_logs',
'webhook_deliveries', 'notifications_queue', 'error_logs'
] LOOP
EXECUTE format(
'CREATE TABLE IF NOT EXISTS %s_%s PARTITION OF %I
FOR VALUES FROM (%L) TO (%L)',
p_name,
TO_CHAR(next_month_start, 'YYYY_MM'),
p_name,
next_month_start, next_month_end
);
RAISE NOTICE 'Created: %s_%s', p_name, TO_CHAR(next_month_start,'YYYY_MM');
END LOOP;
END $$;

-- Verify partitions created
SELECT parent.relname, child.relname, pg_get_expr(child.relpartbound, child.oid)
FROM pg_inherits
JOIN pg_class parent ON parent.oid = pg_inherits.inhparent
JOIN pg_class child  ON child.oid  = pg_inherits.inhrelid
WHERE parent.relname = 'audit_trails'
ORDER BY child.relname;
## B.4 Runbook: Emergency User Data Deletion (GDPR/Privacy Request)
-- Before executing: verify request legitimacy and log in data_deletion_requests
-- Regulatory note: financial records (loans, contracts) CANNOT be deleted
-- Only PII fields are anonymized; records remain for compliance

BEGIN;

-- Step 1: Anonymize PII in users table (soft delete + pseudonymization)
UPDATE users SET
email = 'deleted_user_' || id || '@anonymized.local',
phone = '+9200000' || LPAD(id::TEXT, 7, '0'),
cnic_encrypted = NULL,
cnic_hash = NULL,
first_name = 'DELETED',
last_name = 'USER',
date_of_birth = '1900-01-01',
registration_ip = NULL,
last_login_ip = NULL,
deleted_at = NOW()
WHERE id = $USER_ID;

-- Step 2: Remove KYC documents (delete S3 objects, clear DB references)
UPDATE user_kyc_verifications SET
cnic_front_s3 = NULL, cnic_back_s3 = NULL, selfie_s3 = NULL,
nadra_raw_response = NULL
WHERE user_id = $USER_ID;

-- Step 3: Anonymize addresses
DELETE FROM user_addresses WHERE user_id = $USER_ID AND deleted_at IS NOT NULL;
UPDATE user_addresses SET
address_line_1 = 'DELETED', address_line_2 = NULL,
latitude = NULL, longitude = NULL
WHERE user_id = $USER_ID;

-- Step 4: Remove payment methods (tokenized — invalidate at gateway too)
UPDATE user_payment_methods SET
wallet_number = NULL, iban_encrypted = NULL, card_token = NULL,
deleted_at = NOW()
WHERE user_id = $USER_ID;

-- Step 5: Log the deletion (permanent record of what was done)
UPDATE data_deletion_requests SET
status = 'completed',
executed_at = NOW(),
tables_cleared = ARRAY['users','user_kyc_verifications',
'user_addresses','user_payment_methods']
WHERE user_id = $USER_ID AND status = 'approved';

COMMIT;

# Appendix C: Production Readiness Checklist

# Document Summary & Next Steps
This document completes the SahulatKar BNPL platform database design. Together with Volume I, it delivers a production-ready PostgreSQL database architecture covering all 170+ tables, comprehensive indexing, partitioning, security, disaster recovery, performance optimization, migration strategy, Pakistan-specific data handling, complete audit logging, and 5-year cost projections.
## Volume I Coverage (Sections 1-15)
Technology stack decision: PostgreSQL 16 + Redis 7 + TimescaleDB
Domains: User & Identity (15 tables), Credit & Risk (18 tables), Product & Merchant (10 tables), Order & Purchase (14 tables), Payment & Installment (18 tables), Delivery & Logistics (9 tables), Shariah Compliance (9 tables), Financial Accounting (13 tables), Support & Communications (12 tables), Marketing & Growth (11 tables), Admin & Team (9 tables), Compliance & Audit (9 tables)
## Volume II Coverage (Sections 16-25 + Appendices)
System & Integration domain (12 tables) — complete DDL for all remaining tables
Indexing strategy — 50+ indexes across all tables with justification for each
Partitioning plan — quarterly range partitions, TimescaleDB hypertables, auto-creation via pg_cron
Security architecture — RLS, pgcrypto, user privilege matrix, TLS enforcement
Backup & DR — RTO/RPO objectives, backup schedule, restore procedures, DR drills
Performance optimization — postgresql.conf, PgBouncer, Redis caching strategy, materialized views
Migration strategy — Flyway toolchain, zero-downtime patterns, governance rules
Pakistan-specific — CNIC model, postal codes, mobile operators, Urdu search, SECP compliance
Audit logging — complete coverage matrix, trigger deployment, 7-year archival
Sizing & costs — row projections, storage growth, monthly AWS cost by year
## Immediate Next Steps
SahulatKar Database Architecture — Volume II — March 2026 — CONFIDENTIAL
| Index Type | Use Case | SahulatKar Example |
| --- | --- | --- |
| B-Tree (default) | Equality, range, ORDER BY, LIKE 'prefix%' | users(status), installments(due_date), orders(created_at) |
| Hash | Exact equality only — faster than B-tree for pure = | payment_transactions(gateway_txn_id) — always queried by exact ID |
| GIN | JSONB, full-text, arrays | products(search_vector), audit_trails(changed_fields) |
| GiST | Geospatial (PostGIS), range types | user_addresses(location) for PostGIS distance queries |
| BRIN | Very large tables ordered by insertion time | tracking_events — chronological, huge volume, range scans |
| Partial | Index only rows matching a condition | installments WHERE status='pending' — only query unpaid ones |
| Composite | Multi-column queries together | orders(user_id, status) for user's active orders dashboard |
| Unique Partial | Conditional uniqueness | users(email) WHERE deleted_at IS NULL — allow reuse after deletion |
| Covering | Include non-indexed columns to avoid table heap fetch | orders(user_id) INCLUDE (status, total_amount, created_at) |
| Table | Index Definition | Type | Purpose / Query Pattern |
| --- | --- | --- | --- |
| users | (email) WHERE deleted_at IS NULL | Unique Partial | Login, uniqueness check |
| users | (phone) WHERE deleted_at IS NULL | Unique Partial | Phone login, OTP delivery |
| users | (cnic_hash) WHERE deleted_at IS NULL | Unique Partial | NADRA dedup check |
| users | (status, kyc_status) | B-Tree Composite | Admin KYC review queue |
| users | (registration_ip, created_at DESC) | B-Tree | Velocity/fraud check |
| users | (referred_by_user_id) | B-Tree | Referral tree lookups |
| orders | (user_id, status) | B-Tree Composite | User's orders by state |
| orders | (status, created_at DESC) | B-Tree Composite | State-based processing queues |
| orders | (merchant_id, created_at DESC) | B-Tree Composite | Merchant performance reports |
| orders | (uuid) | Unique | External API lookup by UUID |
| orders | (order_number) | Unique | Support ticket reference |
| loans | (user_id, status) | B-Tree Composite | User's active loans |
| loans | (status) WHERE status<>'fully_paid' | Partial | Active loan portfolio view |
| installments | (due_date, user_id) WHERE status='pending' | Partial Composite | Daily billing sweep |
| installments | (loan_id) WHERE status='pending' | Partial | Loan installment summary |
| installments | (due_date) WHERE status='overdue' | Partial | Overdue escalation job |
| payment_transactions | (installment_id, created_at DESC) | B-Tree Composite | Payment history per installment |
| payment_transactions | (gateway_txn_id) | Hash | Gateway callback reconciliation |
| payment_transactions | (user_id, created_at DESC) | B-Tree Composite | User payment history |
| virtual_cards | (order_id) | Unique | 1:1 order-card lookup |
| virtual_cards | (status) WHERE status='active' | Partial | Active VCN monitoring |
| scraping_jobs | (status, queued_at) WHERE status='queued' | Partial | Job queue dequeue |
| purchase_executions | (order_id, attempt_number) | B-Tree | Retry logic & status check |
| audit_trails | (table_name, record_id) | B-Tree Composite | Entity change history |
| audit_trails | (actor_type, actor_id, changed_at DESC) | B-Tree | Actor activity log |
| fraud_alerts | (user_id, status) | B-Tree Composite | Open fraud alerts per user |
| fraud_alerts | (severity, created_at DESC) | B-Tree Composite | High-severity alert queue |
| murabaha_contracts | (order_id) | Unique | Contract by order |
| shipments | (tracking_number) | Unique | Tracking lookup |
| shipments | (order_id, status) | B-Tree Composite | Order delivery status |
| tracking_events | (shipment_id, event_time DESC) | B-Tree | Last event per shipment |
| notifications_queue | (user_id, channel, created_at DESC) | B-Tree | User notification history |
| notifications_queue | (scheduled_at, priority) WHERE status='queued' | Partial | Dispatch scheduler |
| support_tickets | (user_id, status) | B-Tree Composite | User's open tickets |
| support_tickets | (assigned_to, status) | B-Tree Composite | Agent's work queue |
| products | (canonical_url) | Hash | URL deduplication |
| products | (search_vector) | GIN | Full-text product search |
| products | (merchant_id, is_available) | B-Tree Composite | Merchant catalog view |
| user_addresses | (location) | GiST | PostGIS distance queries |
| admin_activity_logs | (admin_user_id, created_at DESC) | B-Tree | Admin audit trail |
| admin_activity_logs | (target_type, target_id) | B-Tree Composite | Entity-level admin actions |
| journal_entry_lines | (account_id, journal_id) | B-Tree Composite | Account ledger view |
| velocity_checks | (user_id, check_type, checked_at DESC) | B-Tree | Recent velocity per type |
| risk_assessments | (user_id, created_at DESC) | B-Tree | Latest risk score per user |
| promo_code_usage | (promo_code_id, user_id) | Unique Composite | One-per-user enforcement |
| referrals | (referrer_user_id, status) | B-Tree Composite | Referral reward tracking |
| integration_logs | (service_name, created_at DESC) | B-Tree | Service performance metrics |
| error_logs | (severity, resolved) WHERE resolved=FALSE | Partial Composite | Unresolved error triage |
| Strategy | When to Use | SahulatKar Trigger | Complexity |
| --- | --- | --- | --- |
| Declarative Partitioning (single DB) | Single large table >50GB or >100M rows | Year 1 (orders, audit_trails) | Low — PostgreSQL native |
| TimescaleDB Hypertables | Time-series data requiring automatic partitioning + compression | Launch (tracking_events, metrics) | Low — extension only |
| Read Replicas | Read/write ratio > 70:30; reporting overloads primary | Year 1, ~10K DAU | Medium — replication setup |
| Vertical Sharding (separate DBs by domain) | Domain teams own their DB; compliance isolation needed | Year 2, >50K DAU | High — cross-DB joins eliminated |
| Horizontal Sharding (by user_id range) | Single shard >2TB or >50M active users | Year 3+ — evaluate at 1M users | Very High — application-level routing |
| Table | Strategy | Partition Key | Partition Size | Retention Action |
| --- | --- | --- | --- | --- |
| orders | Range quarterly | created_at | ~500K rows/quarter Year 1 | Move to cold after 1 year; archive after 7 years |
| payment_transactions | Range quarterly | created_at | ~2M rows/quarter Year 1 | Retain 7 years; archive old partitions to S3 Parquet |
| audit_trails | Range monthly | changed_at | ~5M rows/month | Retain 7 years; compress at 30 days (TimescaleDB) |
| tracking_events | Range monthly (Timescale) | event_time | ~10M rows/month | Retain 2 years; compress at 7 days |
| admin_activity_logs | Range quarterly | created_at | ~100K rows/quarter | Retain 7 years per compliance |
| integration_logs | Range monthly | created_at | ~20M rows/month | Retain 3 months hot; archive to S3 after |
| scraping_jobs | Range monthly | created_at | ~500K rows/month | Retain 6 months; delete old |
| webhook_deliveries | Range monthly | created_at | ~2M rows/month | Retain 6 months |
| purchase_executions | Range quarterly | created_at | ~500K rows/quarter | Retain 2 years |
| system_health_metrics | Range daily (Timescale) | recorded_at | ~50M rows/day | Compress at 24h; delete at 90 days |
| notifications_queue | Range monthly | created_at | ~3M rows/month | Retain 1 year; delete old |
| error_logs | Range monthly | created_at | ~1M rows/month | Retain 6 months |
| DB User / Role | Tables Accessible | Permissions | Used By |
| --- | --- | --- | --- |
| sk_app | All operational tables | SELECT, INSERT, UPDATE (no DELETE on financial tables) | Main API application pods |
| sk_app_readonly | All tables | SELECT only | User-facing GET requests via replica |
| sk_admin_api | All tables + admin tables | SELECT, INSERT, UPDATE | Admin panel backend |
| sk_billing_worker | loans, installments, payment_transactions, journal_entries | SELECT, INSERT, UPDATE | Billing service workers |
| sk_reporting | All tables (no PII tables) | SELECT only; PII columns masked via views | Analytics & reporting |
| sk_migrations | All tables | All DDL + DML | Migration runner (CI/CD only, short-lived) |
| sk_audit_reader | audit_trails only | SELECT | Compliance officer read-only access |
| sk_superuser | All | SUPERUSER | Break-glass emergency access (MFA required, logged) |
| Layer | Requirement | Implementation |
| --- | --- | --- |
| App → DB | TLS 1.2+ mandatory | AWS RDS: force_ssl=1; reject non-TLS connections via pg_hba.conf |
| DB → Replica | Encrypted WAL streaming | PostgreSQL ssl=on for replication connections |
| Admin → DB | Certificate-based auth + MFA | Client certificates for sk_superuser; never password-only |
| Backup files | Encrypted at rest | AWS S3 SSE-KMS; AES-256 per backup file |
| Disk | Full-disk encryption | AWS EBS encryption with CMK |
| Connection Pooler | TLS frontend | PgBouncer TLS on frontend listener; clear-text only to localhost |
| Scenario | RTO Target | RPO Target | Detection | Recovery Path |
| --- | --- | --- | --- | --- |
| Table corruption (single) | 30 min | 0 (point-in-time) | pgBadger alert | PITR to last consistent checkpoint |
| Database failure (single AZ) | 15 min | 1 min (WAL lag) | CloudWatch alarm | Promote read replica to primary |
| Complete AZ outage | 30 min | 5 min | AWS Health alert | Failover to standby in second AZ |
| Region failure | 2 hours | 1 hour | AWS Health / Pingdom | Restore from cross-region S3 backup |
| Accidental mass delete | 1 hour | 0 (point-in-time) | Developer alert | PITR to minute before delete |
| Ransomware / data corruption | 4 hours | 24 hours | Security monitoring | Restore from immutable S3 backup |
| Activity | Frequency | Procedure | Success Criteria |
| --- | --- | --- | --- |
| Restore Test (table level) | Monthly | Restore single table from weekly backup to test environment | Table row count matches backup manifest within 0.1% |
| Full PITR Test | Quarterly | Restore full DB to target time in isolated environment | All foreign keys valid, row counts match audit log |
| Replica Promotion Drill | Quarterly | Manually promote read replica to primary, test all write operations | Zero data loss, all writes succeed after promotion |
| Cross-Region Restore | Annually | Full restore from S3 cross-region backup | RTO < 4 hours; data integrity validated by checksum |
| Compliance Archive Verify | Annually | Retrieve 3-year-old financial records from Glacier | Records retrievable, readable, and cryptographically intact |
| Cache Key Pattern | TTL | Data Cached | Invalidation Trigger |
| --- | --- | --- | --- |
| user:{id}:profile | 3600s | User status, credit limit, KYC status | On any users table UPDATE |
| user:{id}:active_loans | 60s | Active loan IDs and outstanding totals | On loan UPDATE or installment payment |
| product:{url_hash}:data | 300s | Scraped product data (price, availability) | On product scrape completion |
| order:{uuid}:status | 30s | Current order status (for real-time polling) | On order_state_history INSERT |
| fraud_rules:snapshot | 1800s | All active fraud rule definitions | On fraud_rules table UPDATE |
| merchant:{id}:config | 600s | Merchant scrape config, checkout instructions | On merchants UPDATE |
| feature_flags:all | 60s | All active feature flag states | On feature_flags UPDATE |
| credit:{user_id}:limit | 30s | Available credit (critical for preventing overcommit) | On every loan/installment UPDATE |
| otp:{phone}:{type} | 180s | OTP code for verification (contract signing) | Auto-expire; on use, DELETE |
| session:{token_hash} | 86400s | JWT refresh token validity | On logout/revoke, DELETE |
| rate_limit:{ip}:{endpoint} | 60s | Request count for rate limiting | Auto-expire sliding window |
| vcn:{order_id}:status | 30s | VCN issuer status | On virtual_cards UPDATE |
| Rule | Description | Enforcement |
| --- | --- | --- |
| No direct DDL in production | All schema changes via versioned migrations only | Flyway locks migration table; direct DDL reverts on next deploy |
| One migration per PR | Each feature/fix gets exactly one migration file | PR template checklist |
| Test migrations on staging first | Run migration on staging DB with production-sized data before prod | CI/CD gate: staging must succeed |
| Include rollback notes | Every migration documents how to reverse if needed | Code review requirement |
| Time migrations off-peak | Major migrations (column drops, index rebuilds) run at 2-4AM PKT | Deployment policy |
| Validate with checksums | Flyway validates migration file checksums — modified migrations detected | Flyway built-in |
| Seed data in migrations | Reference data (couriers, currencies, settings) in S__ seed files | Convention |
| Regulation | Data Requirement | Database Implementation |
| --- | --- | --- |
| SECP BNPL Circular 2022 | Customer credit limit disclosure in contract | murabaha_contracts.profit_rate_pct, .profit_amount — mandatory non-null |
| SBP AML/CFT Guidelines | Suspicious transaction reporting | aml_suspicious_activity_reports table; automatic flag on txn > PKR 500,000 |
| PECA 2016 Data Residency | Customer PII must reside in Pakistan | AWS ap-south-1 (Mumbai) or dedicated PK DC; no cross-border PII transfer |
| FATF Compliance | Beneficial ownership records | murabaha_contracts.principal_cnic; wakalah_agreements.principal_name — immutable |
| PMDT (Money Laundering Act) | Transaction monitoring thresholds | velocity_checks with PKR threshold triggers; STR filing integration |
| Pakistan Post Office Act | Delivery address validation | user_addresses.province CHECK constraint against Pakistan provinces only |
| Consumer Protection Act 2019 | Right to cancel within 48 hours | order_cancellations.cancelled_at, business_logic: allow cancel if <48h AND not delivered |
| Table / Event | Audit Required | Trigger Type | Retention | Critical Fields to Log |
| --- | --- | --- | --- | --- |
| users | Yes — Regulatory | DB AFTER trigger | 7 years | status, kyc_status, credit_limit, cnic_verified_at |
| loans | Yes — Regulatory | DB AFTER trigger | 7 years | All financial fields, status, actual_end_date |
| murabaha_contracts | Yes — Shariah & Legal | DB AFTER trigger | Permanent | All fields (contracts are immutable by design) |
| wakalah_agreements | Yes — Shariah & Legal | DB AFTER trigger | Permanent | All fields |
| installments | Yes — Financial | DB AFTER trigger | 7 years | status, paid_amount, paid_at, late_fee_amount |
| payment_transactions | Yes — Financial | DB AFTER trigger | 7 years | All fields (immutable after confirmed) |
| credit_applications | Yes — Compliance | DB AFTER trigger | 7 years | status, decided_at, approved_limit, rejection_code |
| user_kyc_verifications | Yes — Regulatory | DB AFTER trigger | 7 years | status, reviewed_by, nadra_response |
| fraud_alerts | Yes — Compliance | DB AFTER trigger | 7 years | All fields |
| admin_activity_logs | Yes — Internal | Application-level | 7 years | Captured in dedicated table (not audit_trails) |
| orders | Yes — Customer | DB AFTER trigger | 7 years | status transitions, amounts |
| chargebacks | Yes — Financial | DB AFTER trigger | 7 years | All fields |
| user_payment_methods | Yes — PCI | DB AFTER trigger | 7 years | type changes, verification status (never raw card data) |
| credit_limit_history | Yes — Regulatory | INSERT-only design | 7 years | Immutable log — every limit change is a new row |
| user_consent_records | Yes — Legal | INSERT-only design | Permanent | Immutable — consent given/withdrawn, version, timestamp |
| API calls / logins | Yes — Security | Application-level | 3 years | integration_logs, user_sessions |
| Data deletion requests | Yes — Privacy | DB AFTER trigger | 10 years | What was deleted, when, verification steps |
| Table | Year 1 | Year 2 | Year 3 | Year 5 | Avg Row Size | Year 5 Size |
| --- | --- | --- | --- | --- | --- | --- |
| users | 5,000 | 50,000 | 200,000 | 2,000,000 | 500 B | 1 GB |
| orders | 15,000 | 200,000 | 1,000,000 | 12,000,000 | 800 B | 9.6 GB |
| loans | 12,000 | 160,000 | 800,000 | 9,600,000 | 600 B | 5.8 GB |
| installments | 45,000 | 600,000 | 3,200,000 | 38,400,000 | 300 B | 11.5 GB |
| payment_transactions | 50,000 | 700,000 | 3,500,000 | 42,000,000 | 400 B | 16.8 GB |
| audit_trails | 500,000 | 5,000,000 | 25,000,000 | 200,000,000 | 400 B | 80 GB |
| tracking_events | 60,000 | 800,000 | 4,000,000 | 48,000,000 | 200 B | 9.6 GB |
| murabaha_contracts | 12,000 | 160,000 | 800,000 | 9,600,000 | 5,000 B | 48 GB |
| user_kyc_verifications | 5,000 | 50,000 | 200,000 | 2,000,000 | 2,000 B | 4 GB |
| scraping_jobs | 20,000 | 250,000 | 1,200,000 | 14,000,000 | 1,000 B | 14 GB |
| fraud_alerts | 2,000 | 20,000 | 80,000 | 500,000 | 600 B | 0.3 GB |
| notification_queue | 100,000 | 1,200,000 | 6,000,000 | 72,000,000 | 300 B | 21.6 GB |
| integration_logs | 200,000 | 2,500,000 | 12,500,000 | 150,000,000 | 800 B | 120 GB |
| admin_activity_logs | 10,000 | 50,000 | 150,000 | 500,000 | 600 B | 0.3 GB |
| risk_assessments | 15,000 | 200,000 | 1,000,000 | 12,000,000 | 1,500 B | 18 GB |
| Storage Category | Year 1 | Year 2 | Year 3 | Year 5 | Notes |
| --- | --- | --- | --- | --- | --- |
| Primary DB (gp3 SSD) | 50 GB | 200 GB | 800 GB | 4 TB | Includes all active partitions + indexes |
| Read Replicas (×2) | 50 GB each | 200 GB each | 800 GB each | 4 TB each | Same as primary |
| S3: Audit Archive | 5 GB | 50 GB | 250 GB | 2 TB | Parquet compressed (10:1 ratio from raw) |
| S3: KYC/Contract PDFs | 10 GB | 100 GB | 400 GB | 4 TB | Uncompressed PDFs + images |
| S3: DB Backups (weekly) | 50 GB | 200 GB | 800 GB | 4 TB | 30-day rolling retention |
| S3: Compliance Archive | 5 GB | 50 GB | 200 GB | 2 TB | Glacier Deep Archive |
| Redis Cache | 2 GB | 5 GB | 15 GB | 50 GB | 3-node cluster |
| TOTAL | ~170 GB | ~800 GB | ~3.2 TB | ~20 TB | All storage categories combined |
| Component | Specification | Year 1 Monthly | Year 3 Monthly | Year 5 Monthly |
| --- | --- | --- | --- | --- |
| Primary RDS | PostgreSQL r6g.xlarge (32GB) 500GB gp3 | $450 | $900 (r6g.2xlarge) | $2,400 (r6g.4xlarge) |
| Read Replica ×2 | r6g.large per replica 250GB gp3 | $280 | $560 (×2 r6g.xlarge) | $1,800 (×3 r6g.2xlarge) |
| ElastiCache Redis | r6g.large 3-node cluster | $190 | $380 (r6g.xlarge) | $950 (r6g.2xlarge) |
| S3 Storage (all tiers) | Standard + IA + Glacier | $15 | $100 | $500 |
| Data Transfer | Primary → Replica WAL | $20 | $80 | $250 |
| Backup Storage | Automated RDS snapshots | $25 | $80 | $300 |
| CloudWatch / Monitoring | Metrics, logs, alarms | $50 | $100 | $200 |
| PgBouncer (EC2) | t3.small for pooler | $15 | $30 (t3.medium) | $60 (t3.large) |
| TOTAL DATABASE COST |  | $1,045/mo | $2,230/mo | $6,460/mo |
| Per Transaction Cost | (orders/month) | $69.67/1K orders | $11.15/1K orders | $3.23/1K orders |
| Operation | Target Latency | Measurement Point | Failure Threshold |
| --- | --- | --- | --- |
| User login (auth query) | < 50ms p99 | API response time | Alert if >100ms sustained 5 min |
| Order status GET | < 100ms p99 | API response (cache hit) | Alert if >200ms |
| Credit limit check (per order) | < 30ms p99 | DB query + Redis | Alert if >100ms — blocks purchase flow |
| Installment due date sweep | < 60 seconds total | Job duration (100K rows) | Alert if >5 minutes |
| Product URL scrape → extract | < 8 seconds p95 | Job queue to completion | Alert if >30 seconds |
| Payment transaction record | < 100ms p99 | DB write confirmation | Alert if >500ms — financial integrity |
| Fraud velocity check | < 20ms p99 | Redis lookup + DB count | Alert if >100ms — blocks purchase |
| Admin order search | < 500ms p95 | API response (replica) | Alert if >2 seconds |
| Audit trail write | < 50ms p99 | Trigger execution overhead | Alert if >200ms |
| Full-text product search | < 200ms p95 | GIN index query | Alert if >1 second |
| Metric | Current Design Limit | Action Required | Lead Time |
| --- | --- | --- | --- |
| Concurrent connections | 200 (PgBouncer pool: 2000 clients) | Add PgBouncer node or increase max_connections | 1 day |
| Primary DB size | 2 TB (gp3 max performance at this tier) | Upgrade to r6g.2xlarge + 4TB gp3 | 2 hours (RDS scale) |
| Write IOPS | 16,000 IOPS (gp3 provisioned) | Upgrade to io2 or scale instance | 2 hours |
| Replication lag | > 5 seconds sustained | Add read replica, optimize write workload | 1 day |
| Audit trail table size | > 500M rows | Enable TimescaleDB compression + S3 archival | 1 week (migration) |
| Query p99 latency | > 500ms on indexed queries | Review indexes, analyze EXPLAIN plans | 1 week |
| Total users | 1 million active | Evaluate Citus / horizontal sharding | 3 months planning |
| Orders per second | > 100 concurrent inserts | Batch inserts, increase shared_buffers | 1 week |
| Category | Checklist Item | Status |
| --- | --- | --- |
| Schema | All 170+ tables created with correct constraints | Required before launch |
| Schema | All primary keys use BIGSERIAL + UUID pattern | Required before launch |
| Schema | All financial columns use DECIMAL(14,2) not FLOAT | Required before launch |
| Schema | Soft-delete (deleted_at) on all customer-facing tables | Required before launch |
| Schema | Pakistan-specific CHECK constraints on CNIC, phone, province | Required before launch |
| Indexes | Billing sweep index: installments(due_date, user_id) WHERE status='pending' | Required before launch |
| Indexes | All FK columns indexed | Required before launch |
| Indexes | Full-text GIN index on products(search_vector) | Required before launch |
| Indexes | Partial unique indexes for email, phone, CNIC (excluding soft-deleted) | Required before launch |
| Triggers | fn_set_updated_at() on all tables with updated_at column | Required before launch |
| Triggers | fn_log_audit() on all 30 sensitive tables | Required before launch |
| Triggers | fn_generate_order_number() for human-readable IDs | Required before launch |
| Triggers | fn_recalculate_available_credit() on loans table | Required before launch |
| Triggers | fn_apply_late_fee() for Shariah-compliant charity allocation | Required before launch |
| Security | PgBouncer deployed in front of PostgreSQL | Required before launch |
| Security | Row-Level Security enabled on user-data tables | Required before launch |
| Security | CNIC, bank account, MFA secrets encrypted with pgcrypto | Required before launch |
| Security | TLS enforced for all DB connections (force_ssl=1) | Required before launch |
| Security | sk_app user has no DELETE on financial tables | Required before launch |
| Partitioning | orders, payment_transactions partitioned quarterly | Required before launch |
| Partitioning | audit_trails partitioned monthly with 12-month pre-created partitions | Required before launch |
| Partitioning | tracking_events as TimescaleDB hypertable | Required before launch |
| Backup | WAL archiving enabled and tested | Required before launch |
| Backup | Daily automated snapshots configured in AWS RDS | Required before launch |
| Backup | Cross-region S3 backup script deployed and scheduled | Required before launch |
| Backup | PITR restore tested and documented | Required before launch |
| Compliance | All Shariah contract tables with immutable design | Required before launch |
| Compliance | late_fee_charity_allocations trigger verified | Required before launch |
| Compliance | 7-year retention policies documented and configured | Required before launch |
| Compliance | Data deletion runbook tested on staging | Required before launch |
| Performance | pg_stat_statements enabled and baseline captured | Week 1 post-launch |
| Performance | Redis caching deployed for credit limits and fraud rules | Required before launch |
| Performance | Materialized views created and refresh scheduled | Required before launch |
| Performance | PgBouncer pool sizing verified for expected concurrency | Required before launch |
| Seed Data | Pakistan postal codes loaded (11,000+ records) | Required before launch |
| Seed Data | Pakistan mobile operator prefixes loaded | Required before launch |
| Seed Data | Islamic calendar seeded (5 years) | Required before launch |
| Seed Data | Ledger account chart of accounts seeded | Required before launch |
| Seed Data | Couriers seeded with coverage and API config | Required before launch |
| Seed Data | Prohibited categories list seeded and verified by Shariah board | Required before launch |
| Documentation | Data dictionary complete for all tables | Required before launch |
| Documentation | All runbooks tested by operations team | Required before launch |
| Documentation | ERD diagrams published to internal wiki | Required before launch |
| Priority | Action | Owner | Timeline |
| --- | --- | --- | --- |
| P0 | Create flyway migration files from all DDL in Volumes I & II | Backend Lead | Week 1 |
| P0 | Set up PostgreSQL on AWS RDS in ap-south-1 (Pakistan-adjacent) | DevOps | Week 1 |
| P0 | Deploy PgBouncer + configure connection pools | DevOps | Week 1 |
| P0 | Load seed data (postal codes, operators, couriers, ledger accounts) | Backend | Week 1 |
| P0 | Deploy Redis cluster for caching and BullMQ job queues | DevOps | Week 1 |
| P1 | Enable WAL archiving to S3 + configure automated snapshots | DevOps | Week 1 |
| P1 | Implement audit trigger deployment script across all 30 tables | Backend | Week 2 |
| P1 | Set up read replica + configure application-level read routing | DevOps | Week 2 |
| P1 | Verify RLS policies with integration tests | Backend | Week 2 |
| P2 | Set up pg_cron for scheduled tasks (billing, partition creation, archival) | Backend | Week 3 |
| P2 | Create materialized views + refresh schedules | Backend | Week 3 |
| P2 | Implement TimescaleDB hypertables for tracking_events and metrics | Backend | Week 3 |
| P2 | Conduct first PITR restore drill (even on empty DB) | DevOps | Week 4 |
| P3 | Set up Grafana/CloudWatch dashboard for DB health metrics | DevOps | Month 2 |
| P3 | Conduct first load test (pgbench simulation: 1,000 concurrent orders) | QA | Month 2 |