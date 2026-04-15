"""Compliance Admin System Alignment

Revision ID: 035_align_compliance_admin_system
Revises: 034_align_accounting_support_marketing
Create Date: 2026-04-15 05:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '035_align_compliance_admin_system'
down_revision: Union[str, None] = '034_align_accounting_support_marketing'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Compliance Domain Partitioning
    op.execute("DROP TABLE IF EXISTS audit_trails CASCADE")
    op.execute("""
        CREATE TABLE audit_trails (
            id BIGSERIAL,
            table_name VARCHAR(100) NOT NULL,
            record_id BIGINT NOT NULL,
            operation VARCHAR(10) NOT NULL,
            actor_type VARCHAR(20),
            actor_id BIGINT,
            actor_email VARCHAR(255),
            ip_address INET,
            user_agent TEXT,
            request_id UUID,
            session_id UUID,
            old_values JSONB,
            new_values JSONB,
            changed_fields TEXT[],
            change_reason TEXT,
            changed_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, changed_at)
        ) PARTITION BY RANGE (changed_at);
    """)
    op.execute("CREATE TABLE audit_trails_default PARTITION OF audit_trails DEFAULT")

    # 2. System Domain Partitioning & Missing Entities
    op.execute("DROP TABLE IF EXISTS integration_logs CASCADE")
    op.execute("""
        CREATE TABLE integration_logs (
            id BIGSERIAL,
            service_name VARCHAR(50) NOT NULL,
            operation VARCHAR(100) NOT NULL,
            request_id UUID NOT NULL,
            endpoint VARCHAR(512),
            method VARCHAR(10),
            response_code SMALLINT,
            latency_ms INTEGER,
            is_success BOOLEAN,
            error_code VARCHAR(50),
            error_message TEXT,
            user_id BIGINT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at);
    """)
    op.execute("CREATE TABLE intlogs_default PARTITION OF integration_logs DEFAULT")

    op.execute("DROP TABLE IF EXISTS error_logs CASCADE")
    op.execute("""
        CREATE TABLE error_logs (
            id BIGSERIAL,
            error_id UUID NOT NULL DEFAULT gen_random_uuid(),
            service VARCHAR(50) NOT NULL,
            severity VARCHAR(10) NOT NULL,
            message TEXT NOT NULL,
            stack_trace TEXT,
            context JSONB,
            user_id BIGINT,
            request_id UUID,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at);
    """)
    op.execute("CREATE TABLE errlogs_default PARTITION OF error_logs DEFAULT")

    op.execute("DROP TABLE IF EXISTS system_health_metrics CASCADE")
    op.execute("""
        CREATE TABLE system_health_metrics (
            id BIGSERIAL,
            metric_name VARCHAR(100) NOT NULL,
            metric_value DECIMAL(14,4) NOT NULL,
            labels JSONB,
            recorded_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, recorded_at)
        ) PARTITION BY RANGE (recorded_at);
    """)
    op.execute("CREATE TABLE shm_default PARTITION OF system_health_metrics DEFAULT")

    op.create_table(
        "shard_routing",
        sa.Column("user_id_start", sa.BigInteger(), nullable=False),
        sa.Column("user_id_end", sa.BigInteger(), nullable=False),
        sa.Column("shard_name", sa.String(length=50), nullable=False),
        sa.Column("shard_host", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default='true', nullable=False),
        sa.PrimaryKeyConstraint("user_id_start", "user_id_end"),
    )


def downgrade() -> None:
    pass
