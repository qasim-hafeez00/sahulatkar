"""Reapply Triggers After Partition Recreations

Revision ID: 037_reapply_triggers
Revises: 036_complete_partition_sequence
Create Date: 2026-04-15 08:00:00.000000

Fixes CRIT-01 through CRIT-05 from the database gap analysis:
  - CRIT-01: fn_generate_order_number trigger missing on partitioned orders
  - CRIT-02: fn_recalculate_available_credit trigger missing on recreated loans
  - CRIT-03: fn_apply_late_fee trigger missing on recreated installments
  - CRIT-04: Audit triggers missing on all recreated partitioned tables
  - CRIT-05: payment_transactions missing 4 columns
  - CRIT-DB01: updated_at triggers missing on recreated tables
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '037_reapply_triggers'
down_revision: Union[str, None] = '036_complete_partition_sequence'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # CRIT-05: Add missing columns to payment_transactions that were dropped
    # when migration 033 recreated the table as a partitioned table.
    # -------------------------------------------------------------------------
    op.execute("""
        ALTER TABLE payment_transactions
            ADD COLUMN IF NOT EXISTS gateway_response   JSONB,
            ADD COLUMN IF NOT EXISTS retry_of_txn_id   BIGINT,
            ADD COLUMN IF NOT EXISTS settlement_id      BIGINT,
            ADD COLUMN IF NOT EXISTS reconciled_at      TIMESTAMP;
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ptxn_retry_of
            ON payment_transactions (retry_of_txn_id);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ptxn_settlement
            ON payment_transactions (settlement_id)
            WHERE settlement_id IS NOT NULL;
    """)

    # -------------------------------------------------------------------------
    # CRIT-01: Reapply fn_generate_order_number trigger on partitioned orders
    # -------------------------------------------------------------------------
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'trg_generate_order_number'
            ) THEN
                CREATE TRIGGER trg_generate_order_number
                BEFORE INSERT ON orders
                FOR EACH ROW EXECUTE FUNCTION fn_generate_order_number();
            END IF;
        END $$;
    """)

    # -------------------------------------------------------------------------
    # CRIT-02: Reapply fn_recalculate_available_credit trigger on recreated loans
    # -------------------------------------------------------------------------
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'trg_recalculate_credit'
            ) THEN
                CREATE TRIGGER trg_recalculate_credit
                AFTER INSERT OR UPDATE ON loans
                FOR EACH ROW EXECUTE FUNCTION fn_recalculate_available_credit();
            END IF;
        END $$;
    """)

    # -------------------------------------------------------------------------
    # CRIT-03: Reapply fn_apply_late_fee trigger on recreated installments
    # -------------------------------------------------------------------------
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'trg_apply_late_fee'
            ) THEN
                CREATE TRIGGER trg_apply_late_fee
                BEFORE UPDATE ON installments
                FOR EACH ROW EXECUTE FUNCTION fn_apply_late_fee();
            END IF;
        END $$;
    """)

    # -------------------------------------------------------------------------
    # CRIT-04: Reapply audit triggers on all recreated/partitioned tables.
    # Uses DROP-then-CREATE (idempotent) because triggers on partitioned tables
    # cannot be queried reliably via pg_trigger for sub-partition detection.
    # -------------------------------------------------------------------------
    audit_tables = [
        'orders',
        'purchase_executions',
        'loans',
        'installments',
        'payment_transactions',
        'tracking_events',
        'integration_logs',
        'error_logs',
    ]
    for table in audit_tables:
        op.execute(f"""
            DO $$ BEGIN
                IF EXISTS (
                    SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = '{table}'
                ) THEN
                    DROP TRIGGER IF EXISTS trg_audit_{table} ON {table};
                    CREATE TRIGGER trg_audit_{table}
                    AFTER INSERT OR UPDATE OR DELETE ON {table}
                    FOR EACH ROW EXECUTE FUNCTION fn_log_audit();
                END IF;
            END $$;
        """)

    # -------------------------------------------------------------------------
    # CRIT-DB01: Reapply fn_set_updated_at triggers on recreated tables
    # -------------------------------------------------------------------------
    updated_at_tables = ['orders', 'loans', 'installments', 'shipments']
    for table in updated_at_tables:
        op.execute(f"""
            DO $$ BEGIN
                IF EXISTS (
                    SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = '{table}'
                ) THEN
                    DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};
                    CREATE TRIGGER trg_{table}_updated_at
                    BEFORE UPDATE ON {table}
                    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
                END IF;
            END $$;
        """)


def downgrade() -> None:
    # Remove re-applied triggers
    op.execute("DROP TRIGGER IF EXISTS trg_generate_order_number ON orders;")
    op.execute("DROP TRIGGER IF EXISTS trg_recalculate_credit ON loans;")
    op.execute("DROP TRIGGER IF EXISTS trg_apply_late_fee ON installments;")

    audit_tables = [
        'orders', 'purchase_executions', 'loans', 'installments',
        'payment_transactions', 'tracking_events', 'integration_logs', 'error_logs',
    ]
    for table in audit_tables:
        op.execute(f"DROP TRIGGER IF EXISTS trg_audit_{table} ON {table};")

    updated_at_tables = ['orders', 'loans', 'installments', 'shipments']
    for table in updated_at_tables:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};")

    # Remove CRIT-05 added columns
    op.execute("""
        ALTER TABLE payment_transactions
            DROP COLUMN IF EXISTS gateway_response,
            DROP COLUMN IF EXISTS retry_of_txn_id,
            DROP COLUMN IF EXISTS settlement_id,
            DROP COLUMN IF EXISTS reconciled_at;
    """)
