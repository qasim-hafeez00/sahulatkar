"""Missing Database Objects — Partitions, Indexes, Functions, Constraints

Revision ID: 039_missing_db_objects
Revises: 038_missing_domain_tables
Create Date: 2026-04-15 09:00:00.000000

Covers the following from the DB Gap Analysis (April 2026):
  HIGH-01:    Drop prohibited_item_logs (incorrect name from migration 007)
  HIGH-DB02:  2026 Q1-Q4 partitions for orders, payment_transactions,
              purchase_executions, notifications_queue, audit_trails
  HIGH-DB03:  Missing indexes on recreated partitioned tables
  HIGH-DB04:  Scheduled task seeds for materialized view refresh
  HIGH-DB05:  fn_get_wallet_options utility function (Volume 2 §23.3)
  MED-DB06:   fn_is_payment_holiday utility function (Volume 2 §23.4)
  MED-DB07:   NOT NULL + positive-value constraints on murabaha_contracts
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '039_missing_db_objects'
down_revision: Union[str, None] = '038_missing_domain_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # HIGH-01: Drop incorrectly named duplicate table.
    # Migration 007 created prohibited_item_logs (no 's' before 'log').
    # Migration 033 created the spec-correct prohibited_items_log.
    # Both exist simultaneously — drop the wrong one.
    # -------------------------------------------------------------------------
    op.execute("DROP TABLE IF EXISTS prohibited_item_logs CASCADE;")

    # -------------------------------------------------------------------------
    # HIGH-DB02: 2026 partition tables.
    # Migration 036 only covered 2025. The system is now live in 2026 Q1/Q2.
    # -------------------------------------------------------------------------

    # Orders — quarterly (2026 Q1-Q4)
    op.execute("CREATE TABLE IF NOT EXISTS orders_2026_q1 PARTITION OF orders FOR VALUES FROM ('2026-01-01') TO ('2026-04-01');")
    op.execute("CREATE TABLE IF NOT EXISTS orders_2026_q2 PARTITION OF orders FOR VALUES FROM ('2026-04-01') TO ('2026-07-01');")
    op.execute("CREATE TABLE IF NOT EXISTS orders_2026_q3 PARTITION OF orders FOR VALUES FROM ('2026-07-01') TO ('2026-10-01');")
    op.execute("CREATE TABLE IF NOT EXISTS orders_2026_q4 PARTITION OF orders FOR VALUES FROM ('2026-10-01') TO ('2027-01-01');")

    # Payment Transactions — quarterly (2026 Q1-Q4)
    op.execute("CREATE TABLE IF NOT EXISTS ptxn_2026_q1 PARTITION OF payment_transactions FOR VALUES FROM ('2026-01-01') TO ('2026-04-01');")
    op.execute("CREATE TABLE IF NOT EXISTS ptxn_2026_q2 PARTITION OF payment_transactions FOR VALUES FROM ('2026-04-01') TO ('2026-07-01');")
    op.execute("CREATE TABLE IF NOT EXISTS ptxn_2026_q3 PARTITION OF payment_transactions FOR VALUES FROM ('2026-07-01') TO ('2026-10-01');")
    op.execute("CREATE TABLE IF NOT EXISTS ptxn_2026_q4 PARTITION OF payment_transactions FOR VALUES FROM ('2026-10-01') TO ('2027-01-01');")

    # Purchase Executions — quarterly (2026 Q1-Q4)
    op.execute("CREATE TABLE IF NOT EXISTS pe_2026_q1 PARTITION OF purchase_executions FOR VALUES FROM ('2026-01-01') TO ('2026-04-01');")
    op.execute("CREATE TABLE IF NOT EXISTS pe_2026_q2 PARTITION OF purchase_executions FOR VALUES FROM ('2026-04-01') TO ('2026-07-01');")
    op.execute("CREATE TABLE IF NOT EXISTS pe_2026_q3 PARTITION OF purchase_executions FOR VALUES FROM ('2026-07-01') TO ('2026-10-01');")
    op.execute("CREATE TABLE IF NOT EXISTS pe_2026_q4 PARTITION OF purchase_executions FOR VALUES FROM ('2026-10-01') TO ('2027-01-01');")

    # Notifications Queue — quarterly (2026 Q1-Q4)
    op.execute("CREATE TABLE IF NOT EXISTS nq_2026_q1 PARTITION OF notifications_queue FOR VALUES FROM ('2026-01-01') TO ('2026-04-01');")
    op.execute("CREATE TABLE IF NOT EXISTS nq_2026_q2 PARTITION OF notifications_queue FOR VALUES FROM ('2026-04-01') TO ('2026-07-01');")
    op.execute("CREATE TABLE IF NOT EXISTS nq_2026_q3 PARTITION OF notifications_queue FOR VALUES FROM ('2026-07-01') TO ('2026-10-01');")
    op.execute("CREATE TABLE IF NOT EXISTS nq_2026_q4 PARTITION OF notifications_queue FOR VALUES FROM ('2026-10-01') TO ('2027-01-01');")

    # Tracking Events — quarterly (2026 Q1-Q4)
    op.execute("CREATE TABLE IF NOT EXISTS te_2026_q1 PARTITION OF tracking_events FOR VALUES FROM ('2026-01-01') TO ('2026-04-01');")
    op.execute("CREATE TABLE IF NOT EXISTS te_2026_q2 PARTITION OF tracking_events FOR VALUES FROM ('2026-04-01') TO ('2026-07-01');")
    op.execute("CREATE TABLE IF NOT EXISTS te_2026_q3 PARTITION OF tracking_events FOR VALUES FROM ('2026-07-01') TO ('2026-10-01');")
    op.execute("CREATE TABLE IF NOT EXISTS te_2026_q4 PARTITION OF tracking_events FOR VALUES FROM ('2026-10-01') TO ('2027-01-01');")

    # Audit Trails — monthly (2026 Jan-Dec)
    audit_months_2026 = [
        ('m01', '2026-01-01', '2026-02-01'),
        ('m02', '2026-02-01', '2026-03-01'),
        ('m03', '2026-03-01', '2026-04-01'),
        ('m04', '2026-04-01', '2026-05-01'),
        ('m05', '2026-05-01', '2026-06-01'),
        ('m06', '2026-06-01', '2026-07-01'),
        ('m07', '2026-07-01', '2026-08-01'),
        ('m08', '2026-08-01', '2026-09-01'),
        ('m09', '2026-09-01', '2026-10-01'),
        ('m10', '2026-10-01', '2026-11-01'),
        ('m11', '2026-11-01', '2026-12-01'),
        ('m12', '2026-12-01', '2027-01-01'),
    ]
    for label, start, end in audit_months_2026:
        op.execute(
            f"CREATE TABLE IF NOT EXISTS audit_trails_2026_{label} "
            f"PARTITION OF audit_trails FOR VALUES FROM ('{start}') TO ('{end}');"
        )

    # -------------------------------------------------------------------------
    # HIGH-DB03: Missing indexes on recreated partitioned tables.
    # These were removed when migrations 032-033 dropped and recreated tables.
    # -------------------------------------------------------------------------

    # Orders
    op.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_status    ON orders (user_id, status);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_orders_status_created ON orders (status, created_at DESC);")
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_orders_merchant_created
            ON orders (merchant_id, created_at DESC)
            WHERE merchant_id IS NOT NULL;
    """)

    # Installments — critical for daily billing sweep
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_inst_billing
            ON installments (due_date, user_id)
            WHERE status = 'pending';
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_inst_overdue
            ON installments (due_date)
            WHERE status = 'overdue';
    """)

    # Payment Transactions — critical for gateway reconciliation
    op.execute("CREATE INDEX IF NOT EXISTS idx_ptxn_installment  ON payment_transactions (installment_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ptxn_user_created ON payment_transactions (user_id, created_at DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ptxn_status       ON payment_transactions (status);")

    # -------------------------------------------------------------------------
    # HIGH-DB04: Seed scheduled_tasks for nightly materialized view refreshes.
    # The MVs were created in migration 029 but never registered for refresh.
    # -------------------------------------------------------------------------
    op.execute("""
        INSERT INTO scheduled_tasks (task_name, schedule_cron, is_active) VALUES
            ('refresh_mv_daily_revenue',        '0 20 * * *', true),
            ('refresh_mv_loan_portfolio',        '0 20 * * *', true),
            ('refresh_mv_merchant_performance',  '30 20 * * *', true)
        ON CONFLICT (task_name) DO NOTHING;
    """)
    # Note: cron is in UTC — '0 20 * * *' = 01:00 PKT (+5:00)

    # -------------------------------------------------------------------------
    # HIGH-DB05: fn_get_wallet_options  (Volume 2 §23.3)
    # Determines which mobile wallet options are available for a given phone.
    # Used by the payment method selection UI.
    # -------------------------------------------------------------------------
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_get_wallet_options(phone TEXT)
        RETURNS TEXT[] AS $$
        DECLARE
            v_prefix  TEXT    := LEFT(phone, 7);
            v_options TEXT[]  := '{}';
        BEGIN
            SELECT ARRAY_REMOVE(ARRAY[
                CASE WHEN supports_jazzcash   THEN 'jazzcash'   END,
                CASE WHEN supports_easypaisa  THEN 'easypaisa'  END
            ], NULL) INTO v_options
            FROM pk_mobile_prefixes
            WHERE prefix = v_prefix;

            RETURN COALESCE(v_options, ARRAY['bank_account']);
        END;
        $$ LANGUAGE plpgsql STABLE;
    """)

    # -------------------------------------------------------------------------
    # MED-DB06: fn_is_payment_holiday  (Volume 2 §23.4)
    # Used by billing sweep scheduler to skip Eid and public holiday dates.
    # -------------------------------------------------------------------------
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_is_payment_holiday(check_date DATE)
        RETURNS BOOLEAN AS $$
            SELECT COALESCE(
                (
                    SELECT (is_public_holiday OR is_eid_ul_fitr OR is_eid_ul_adha)
                    FROM   islamic_calendar
                    WHERE  gregorian_date = check_date
                ),
                FALSE
            );
        $$ LANGUAGE SQL STABLE;
    """)

    # -------------------------------------------------------------------------
    # MED-DB07: Enforce Shariah hard constraints on murabaha_contracts.
    # Volume 1 §10 Rule 2 mandates cost_price, profit_amount, profit_rate_pct
    # must be NOT NULL and strictly positive.
    # -------------------------------------------------------------------------
    # Use DO block to only alter if columns are currently nullable
    op.execute("""
        DO $$ BEGIN
            -- Enforce NOT NULL at database level
            ALTER TABLE murabaha_contracts
                ALTER COLUMN cost_price      SET NOT NULL,
                ALTER COLUMN profit_amount   SET NOT NULL,
                ALTER COLUMN profit_rate_pct SET NOT NULL;
        EXCEPTION
            WHEN others THEN
                RAISE NOTICE 'murabaha_contracts NOT NULL constraint already applied or table does not exist: %', SQLERRM;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE murabaha_contracts
                ADD CONSTRAINT chk_murabaha_positive_profit
                    CHECK (profit_amount > 0 AND profit_rate_pct > 0 AND cost_price > 0);
        EXCEPTION
            WHEN duplicate_object THEN
                RAISE NOTICE 'Constraint chk_murabaha_positive_profit already exists.';
        END $$;
    """)


def downgrade() -> None:
    # Remove Murabaha constraints
    op.execute("""
        ALTER TABLE murabaha_contracts
            DROP CONSTRAINT IF EXISTS chk_murabaha_positive_profit;
    """)

    # Remove utility functions
    op.execute("DROP FUNCTION IF EXISTS fn_is_payment_holiday(DATE);")
    op.execute("DROP FUNCTION IF EXISTS fn_get_wallet_options(TEXT);")

    # Remove scheduled task seeds
    op.execute("""
        DELETE FROM scheduled_tasks
        WHERE task_name IN (
            'refresh_mv_daily_revenue',
            'refresh_mv_loan_portfolio',
            'refresh_mv_merchant_performance'
        );
    """)

    # Drop 2026 partitions — order matters (child before parent not needed for
    # partitions, but list explicitly to avoid ambiguity)
    for label, _, _ in [
        ('m01','',''),('m02','',''),('m03','',''),('m04','',''),
        ('m05','',''),('m06','',''),('m07','',''),('m08','',''),
        ('m09','',''),('m10','',''),('m11','',''),('m12','',''),
    ]:
        op.execute(f"DROP TABLE IF EXISTS audit_trails_2026_{label};")

    for q in ['q1','q2','q3','q4']:
        op.execute(f"DROP TABLE IF EXISTS orders_2026_{q};")
        op.execute(f"DROP TABLE IF EXISTS ptxn_2026_{q};")
        op.execute(f"DROP TABLE IF EXISTS pe_2026_{q};")
        op.execute(f"DROP TABLE IF EXISTS nq_2026_{q};")
        op.execute(f"DROP TABLE IF EXISTS te_2026_{q};")

    # Note: prohibited_item_logs cannot be restored in downgrade
    # as the original data is lost on DROP.
