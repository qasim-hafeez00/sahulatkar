"""Add severity to gateway_audit_events

Revision ID: 064
Revises: 063
Create Date: 2026-07-04 00:00:00.000000

Module 8 (Compliance & Audit) — destructive admin actions (suspend/close
user, blacklist, credit-limit increases above the approval threshold,
restructuring, refunds) are tagged severity='critical' so they surface in
the dedicated critical-actions feed super_admins monitor.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '064'
down_revision: Union[str, None] = '063'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "gateway_audit_events",
        sa.Column("severity", sa.String(length=10), nullable=False, server_default="info"),
    )
    op.create_check_constraint(
        "chk_gateway_audit_events_severity",
        "gateway_audit_events",
        "severity IN ('info', 'warning', 'critical')",
    )
    op.create_index(
        "ix_gateway_audit_events_severity_created_at",
        "gateway_audit_events",
        ["severity", "created_at"],
        unique=False,
    )
    for role in ("sk_app", "sk_admin"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON gateway_audit_events TO {role}")


def downgrade() -> None:
    op.drop_index("ix_gateway_audit_events_severity_created_at", table_name="gateway_audit_events")
    op.drop_constraint("chk_gateway_audit_events_severity", "gateway_audit_events", type_="check")
    op.drop_column("gateway_audit_events", "severity")
