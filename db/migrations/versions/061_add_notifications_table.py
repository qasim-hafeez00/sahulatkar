"""Add notifications table

Revision ID: 061
Revises: 060
Create Date: 2026-07-03 00:00:09.000000

The Notification model in sk_shared.models.notification never had a migration
creating its table -- the in-app customer notification inbox has no backing
table until now. NotificationDispatch/Template/Preference/ScheduledNotification
are left uncreated since nothing in gateway queries them yet.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '061'
down_revision: Union[str, None] = '060'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("source_event", sa.String(length=100), nullable=False),
        sa.Column("source_reference", sa.String(length=200), nullable=True),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="normal"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("channels_requested", sa.JSON(), nullable=False),
        sa.Column("template_vars", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_notifications_user_created", "notifications", ["user_id", "created_at"], unique=False)
    op.create_index("ix_notifications_status", "notifications", ["status"], unique=False)
    op.create_index("ix_notifications_source_event", "notifications", ["source_event"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_notifications_source_event", table_name="notifications")
    op.drop_index("ix_notifications_status", table_name="notifications")
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_table("notifications")
