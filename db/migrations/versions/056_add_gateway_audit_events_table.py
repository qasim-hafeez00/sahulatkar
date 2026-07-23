"""Add gateway_audit_events table expected by the AuditTrail ORM model

Revision ID: 056
Revises: 055
Create Date: 2026-07-03 00:00:04.000000

Same class of drift as 052/053: sk_shared.models.audit.AuditTrail (used by
src/core/audit.py::record_audit_event across contracts/payments/orders/kyc
routes) is explicitly documented as "application-level audit events (distinct
from DB trigger-based row audit)" and expects its own dedicated
`gateway_audit_events` table — separate from the legacy trigger-fed, monthly
partitioned `audit_trails` table already present in this database. That
dedicated table never existed, so every audited action failed outright.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '056'
down_revision: Union[str, None] = '055'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gateway_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("admin_user_id", sa.BigInteger(), sa.ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("customer_user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("module", sa.String(50), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_id", sa.BigInteger(), nullable=True),
        sa.Column("changes", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_gateway_audit_events_customer_user_id", "gateway_audit_events", ["customer_user_id"])
    op.create_index("ix_gateway_audit_events_module_action", "gateway_audit_events", ["module", "action"])


def downgrade() -> None:
    op.drop_index("ix_gateway_audit_events_module_action", table_name="gateway_audit_events")
    op.drop_index("ix_gateway_audit_events_customer_user_id", table_name="gateway_audit_events")
    op.drop_table("gateway_audit_events")
