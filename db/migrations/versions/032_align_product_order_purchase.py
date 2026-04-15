"""Product Order Purchase Alignment

Revision ID: 032_align_product_order_purchase
Revises: 031_align_user_credit_fraud
Create Date: 2026-04-15 04:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '032_align_product_order_purchase'
down_revision: Union[str, None] = '031_align_user_credit_fraud'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0. Drop existing tables to enable partitioning
    # Note: Dependent tables like loans, installments, etc. will be recreated in 033
    op.execute("DROP TABLE IF EXISTS purchase_executions CASCADE")
    op.execute("DROP TABLE IF EXISTS orders CASCADE")
    op.execute("DROP TABLE IF EXISTS order_status_history CASCADE")
    op.execute("DROP TABLE IF EXISTS order_state_history CASCADE")

    # 1. Order Domain (PARTITIONED)
    op.execute("""
        CREATE TABLE orders (
            id BIGSERIAL,
            uuid UUID NOT NULL DEFAULT gen_random_uuid(),
            order_number VARCHAR(30) NOT NULL,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            input_url VARCHAR(2048) NOT NULL,
            canonical_url VARCHAR(2048),
            merchant_id BIGINT REFERENCES merchants(id),
            product_id BIGINT REFERENCES products(id),
            scraping_job_id BIGINT,
            status VARCHAR(30) NOT NULL DEFAULT 'url_submitted',
            product_snapshot JSONB NOT NULL,
            selected_variant JSONB,
            product_cost DECIMAL(14,2) NOT NULL,
            platform_profit DECIMAL(14,2) NOT NULL,
            total_amount DECIMAL(14,2) NOT NULL,
            currency CHAR(3) NOT NULL DEFAULT 'PKR',
            delivery_address_id BIGINT,
            delivery_address_snapshot JSONB,
            risk_assessment_id BIGINT,
            down_payment_amount DECIMAL(14,2),
            down_payment_pct DECIMAL(5,2),
            merchant_order_id VARCHAR(255),
            merchant_order_url VARCHAR(2048),
            cancelled_at TIMESTAMP,
            cancel_reason VARCHAR(100),
            cancelled_by VARCHAR(20),
            admin_notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at);
    """)

    op.create_index("idx_orders_uuid", "orders", ["uuid"], unique=False)
    op.create_index("idx_orders_number", "orders", ["order_number"], unique=False)

    # Partitions
    op.execute("CREATE TABLE orders_2025_q1 PARTITION OF orders FOR VALUES FROM ('2025-01-01') TO ('2025-04-01')")
    op.execute("CREATE TABLE orders_2025_q2 PARTITION OF orders FOR VALUES FROM ('2025-04-01') TO ('2025-07-01')")
    op.execute("CREATE TABLE orders_2025_q3 PARTITION OF orders FOR VALUES FROM ('2025-07-01') TO ('2025-10-01')")
    op.execute("CREATE TABLE orders_2025_q4 PARTITION OF orders FOR VALUES FROM ('2025-10-01') TO ('2026-01-01')")
    op.execute("CREATE TABLE orders_default PARTITION OF orders DEFAULT")

    op.create_table(
        "order_state_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("from_status", sa.String(length=30), nullable=True),
        sa.Column("to_status", sa.String(length=30), nullable=False),
        sa.Column("transition_reason", sa.String(length=255), nullable=True),
        sa.Column("triggered_by", sa.String(length=20), nullable=True),
        sa.Column("triggered_by_id", sa.BigInteger(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # 2. Purchase Domain Partitioning
    op.execute("""
        CREATE TABLE purchase_executions (
            id BIGSERIAL,
            uuid UUID NOT NULL DEFAULT gen_random_uuid(),
            order_id BIGINT NOT NULL,
            vcn_id BIGINT,
            attempt_number SMALLINT NOT NULL DEFAULT 1,
            worker_id VARCHAR(100),
            proxy_used VARCHAR(100),
            status VARCHAR(30) NOT NULL DEFAULT 'queued',
            step_reached VARCHAR(50),
            failure_type VARCHAR(50),
            error_detail TEXT,
            screenshot_s3 VARCHAR(512),
            merchant_order_id VARCHAR(255),
            merchant_order_url VARCHAR(2048),
            receipt_screenshot_s3 VARCHAR(512),
            duration_ms INTEGER,
            queued_at TIMESTAMP NOT NULL DEFAULT NOW(),
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at);
    """)
    op.create_index("idx_pe_uuid", "purchase_executions", ["uuid"], unique=False)
    op.execute("CREATE TABLE pe_2025_q1 PARTITION OF purchase_executions FOR VALUES FROM ('2025-01-01') TO ('2025-04-01')")
    op.execute("CREATE TABLE pe_default PARTITION OF purchase_executions DEFAULT")


def downgrade() -> None:
    pass
