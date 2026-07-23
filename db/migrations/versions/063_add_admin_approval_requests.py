"""Add admin_approval_requests table

Revision ID: 063
Revises: 062
Create Date: 2026-07-04 00:00:00.000000

Generic manager-approval workflow table. First consumer is Module 2 (Users)
credit-limit increases above PKR 100,000; Module 4 (Payments) restructuring
approvals reuse the same table rather than each module growing its own
parallel approval mechanism.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '063'
down_revision: Union[str, None] = '062'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_approval_requests",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("request_type", sa.String(length=50), nullable=False),
        sa.Column("entity_type", sa.String(length=30), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=False),
        sa.Column("requested_by", sa.BigInteger(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column("decided_by", sa.BigInteger(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending','approved','rejected')"),
        sa.ForeignKeyConstraint(["requested_by"], ["admin_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["decided_by"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index(
        "ix_admin_approval_requests_status_created_at",
        "admin_approval_requests",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_admin_approval_requests_entity",
        "admin_approval_requests",
        ["entity_type", "entity_id"],
        unique=False,
    )
    # Tables created via migrations (run as the postgres superuser) don't
    # inherit the sk_app/sk_admin grants that pre-existing tables were given
    # by the original DB provisioning script — grant explicitly so the app
    # roles can actually read/write this table.
    for role in ("sk_app", "sk_admin"):
        op.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON admin_approval_requests TO {role}"
        )
        op.execute(f"GRANT USAGE, SELECT ON admin_approval_requests_id_seq TO {role}")


def downgrade() -> None:
    op.drop_table("admin_approval_requests")
