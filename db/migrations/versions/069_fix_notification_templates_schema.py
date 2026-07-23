"""Fix notification_templates schema drift, add missing notification_dispatches

Revision ID: 069
Revises: 068
Create Date: 2026-07-04 00:00:00.000000

Migration 027 created an older notification_templates (name, channel_id ->
notification_channels) that migration 061 never migrated away from, even
though the NotificationTemplate/NotificationDispatch ORM models (written
against the newer notifications/notification_templates design) expect a
completely different shape (event_type, channel, language) and an entirely
separate notification_dispatches table that was never created at all.

Verified zero consumers of the old notification_templates shape anywhere in
the codebase (grep confirms only this migration's own admin_notifications.py
addition touches NotificationTemplate) and the table is empty, so dropping
and recreating it under the same name is safe. notification_channels is left
alone as dead schema, consistent with this codebase's existing convention
for retired duplicate tables (see Module 8's audit-table consolidation note).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '069'
down_revision: Union[str, None] = '068'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("notification_templates")

    op.create_table(
        "notification_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False, server_default="en"),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("body_template", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.CheckConstraint("channel IN ('sms','whatsapp','push','email')"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_type", "channel", "language", name="uq_template_event_channel_lang"),
    )

    op.create_table(
        "notification_dispatches",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("notification_id", sa.BigInteger(), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("provider_name", sa.String(length=50), nullable=True),
        sa.Column("rendered_content", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("failed_at", sa.DateTime(), nullable=True),
        sa.Column("failure_reason", sa.String(length=500), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("channel IN ('sms','whatsapp','push','email')"),
        sa.CheckConstraint("status IN ('pending','sent','delivered','failed','retrying','dlq')"),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("notification_id", "channel", name="uq_dispatch_notification_channel"),
    )
    op.create_index(
        "ix_dispatch_status_retry", "notification_dispatches", ["status", "next_retry_at"], unique=False
    )
    op.create_index(
        "ix_notification_dispatches_notification_id", "notification_dispatches", ["notification_id"], unique=False
    )

    for table in ("notification_templates", "notification_dispatches"):
        for role in ("sk_app", "sk_admin"):
            op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {role}")
    for role in ("sk_app", "sk_admin"):
        op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}")


def downgrade() -> None:
    op.drop_table("notification_dispatches")
    op.drop_table("notification_templates")
    op.create_table(
        "notification_templates",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("channel_id", sa.SmallInteger(), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("body_template", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["notification_channels.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "channel_id"),
    )
