"""Accounting Support Marketing Alignment

Revision ID: 034_align_accounting_support_marketing
Revises: 033_align_payment_delivery_shariah
Create Date: 2026-04-15 04:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '034_align_accounting_support_marketing'
down_revision: Union[str, None] = '033_align_payment_delivery_shariah'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Support Domain Partitioning
    op.execute("DROP TABLE IF EXISTS notifications_queue CASCADE")
    op.execute("""
        CREATE TABLE notifications_queue (
            id BIGSERIAL,
            uuid UUID NOT NULL DEFAULT gen_random_uuid(),
            user_id BIGINT NOT NULL REFERENCES users(id),
            channel VARCHAR(20) NOT NULL,
            notification_type VARCHAR(50) NOT NULL,
            template_id BIGINT,
            subject VARCHAR(255),
            body TEXT NOT NULL,
            variables JSONB,
            recipient VARCHAR(255) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'queued',
            priority SMALLINT NOT NULL DEFAULT 5,
            scheduled_at TIMESTAMP,
            sent_at TIMESTAMP,
            delivered_at TIMESTAMP,
            failure_reason TEXT,
            retry_count SMALLINT NOT NULL DEFAULT 0,
            gateway_message_id VARCHAR(255),
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at);
    """)
    op.create_index("idx_nq_uuid", "notifications_queue", ["uuid"], unique=False)
    op.execute("CREATE TABLE nq_2025_q1 PARTITION OF notifications_queue FOR VALUES FROM ('2025-01-01') TO ('2025-04-01')")
    op.execute("CREATE TABLE nq_default PARTITION OF notifications_queue DEFAULT")


def downgrade() -> None:
    pass
