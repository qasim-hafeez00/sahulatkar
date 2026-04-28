"""Payment Delivery Shariah Alignment

Revision ID: 033_align_payment_delivery_shariah
Revises: 032_align_product_order_purchase
Create Date: 2026-04-15 04:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '033_align_payment_delivery_shariah'
down_revision: Union[str, None] = '032_align_product_order_purchase'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0. Ensure tables are dropped before re-creation to handle partitioning/structural changes
    op.execute("DROP TABLE IF EXISTS installments CASCADE")
    op.execute("DROP TABLE IF EXISTS loans CASCADE")

    # 1. Loan Domain Re-creation
    op.create_table(
        "loans",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("loan_number", sa.String(length=30), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("murabaha_contract_id", sa.BigInteger(), nullable=True),
        sa.Column("principal_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("profit_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_repayable", sa.Numeric(14, 2), nullable=False),
        sa.Column("down_payment_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("balance_financed", sa.Numeric(14, 2), nullable=False),
        sa.Column("profit_rate_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("plan_type", sa.String(length=20), nullable=False),
        sa.Column("installment_count", sa.SmallInteger(), nullable=False),
        sa.Column("installment_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(length=20), server_default='active', nullable=False),
        sa.Column("total_paid", sa.Numeric(14, 2), server_default='0', nullable=False),
        sa.Column("total_outstanding", sa.Numeric(14, 2), nullable=False),
        sa.Column("late_fee_total", sa.Numeric(14, 2), server_default='0', nullable=False),
        sa.Column("last_payment_date", sa.DateTime(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("expected_end_date", sa.Date(), nullable=False),
        sa.Column("actual_end_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("loan_number"),
        sa.UniqueConstraint("uuid"),
    )

    op.create_table(
        "installments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("loan_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("installment_number", sa.SmallInteger(), nullable=False),
        sa.Column("is_down_payment", sa.Boolean(), server_default='false', nullable=False),
        sa.Column("principal_portion", sa.Numeric(14, 2), nullable=False),
        sa.Column("profit_portion", sa.Numeric(14, 2), server_default='0', nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default='pending', nullable=False),
        sa.Column("paid_amount", sa.Numeric(14, 2), server_default='0', nullable=False),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("days_overdue", sa.Integer(), server_default='0', nullable=False),
        sa.Column("late_fee_amount", sa.Numeric(14, 2), server_default='0', nullable=False),
        sa.Column("late_fee_waived", sa.Boolean(), server_default='false', nullable=False),
        sa.Column("late_fee_waiver_reason", sa.Text(), nullable=True),
        sa.Column("reminders_sent", sa.SmallInteger(), server_default='0', nullable=False),
        sa.Column("last_reminder_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["loan_id"], ["loans.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )

    # 1. Payment Domain Partitioning
    op.execute("DROP TABLE IF EXISTS payment_transactions CASCADE")
    op.execute("""
        CREATE TABLE payment_transactions (
            id BIGSERIAL,
            uuid UUID NOT NULL DEFAULT gen_random_uuid(),
            installment_id BIGINT NOT NULL REFERENCES installments(id) ON DELETE RESTRICT,
            user_id BIGINT NOT NULL REFERENCES users(id),
            payment_method_id BIGINT,
            amount DECIMAL(14,2) NOT NULL,
            currency CHAR(3) NOT NULL DEFAULT 'PKR',
            gateway VARCHAR(30) NOT NULL,
            gateway_txn_id VARCHAR(255),
            gateway_order_id VARCHAR(255),
            status VARCHAR(30) NOT NULL DEFAULT 'initiated',
            failure_code VARCHAR(50),
            failure_message TEXT,
            initiated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            confirmed_at TIMESTAMP,
            failed_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at);
    """)
    op.create_index("idx_ptxn_uuid", "payment_transactions", ["uuid"], unique=False)
    op.create_index("idx_ptxn_gateway_txn", "payment_transactions", ["gateway_txn_id"], unique=False)
    op.execute("CREATE TABLE ptxn_2025_q1 PARTITION OF payment_transactions FOR VALUES FROM ('2025-01-01') TO ('2025-04-01')")
    op.execute("CREATE TABLE ptxn_default PARTITION OF payment_transactions DEFAULT")

    # 2. Delivery Domain Partitioning
    op.execute("DROP TABLE IF EXISTS tracking_events CASCADE")
    op.execute("""
        CREATE TABLE tracking_events (
            id BIGSERIAL,
            shipment_id BIGINT NOT NULL,
            event_code VARCHAR(50),
            event_description TEXT,
            location_city VARCHAR(100),
            courier_raw_data JSONB,
            event_time TIMESTAMP NOT NULL,
            received_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, event_time)
        ) PARTITION BY RANGE (event_time);
    """)
    op.execute("CREATE TABLE te_default PARTITION OF tracking_events DEFAULT")

    # 3. Shariah Domain Missing Entity
    op.create_table(
        "prohibited_items_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("product_url", sa.String(length=2048), nullable=False),
        sa.Column("detected_category", sa.String(length=100), nullable=True),
        sa.Column("block_reason", sa.Text(), nullable=True),
        sa.Column("blocked_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("prohibited_items_log")
    op.execute("DROP TABLE IF EXISTS te_default CASCADE")
    op.execute("DROP TABLE IF EXISTS tracking_events CASCADE")
    op.execute("DROP TABLE IF EXISTS ptxn_default CASCADE")
    op.execute("DROP TABLE IF EXISTS ptxn_2025_q1 CASCADE")
    op.execute("DROP TABLE IF EXISTS payment_transactions CASCADE")
    op.drop_table("installments")
    op.drop_table("loans")
