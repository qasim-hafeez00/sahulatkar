"""Notification service tables

Revision ID: 049
Revises: 048
Create Date: 2026-04-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '049'
down_revision: Union[str, None] = '048'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guard: skip if tables were already created by an earlier migration
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name='notification_templates'"
    )).scalar()
    if result:
        return

    # notifications
    op.create_table('notifications',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('source_event', sa.String(length=100), nullable=False),
        sa.Column('source_reference', sa.String(length=200), nullable=True),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('priority', sa.String(length=20), nullable=False, server_default='normal'),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='queued'),
        sa.Column('idempotency_key', sa.String(length=255), nullable=False),
        sa.Column('channels_requested', postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key')
    )
    op.create_index('ix_notifications_source_event', 'notifications', ['source_event'], unique=False)
    op.create_index('ix_notifications_status', 'notifications', ['status'], unique=False)
    op.create_index('ix_notifications_user_created', 'notifications', ['user_id', 'created_at'], unique=False)

    # notification_dispatches
    op.create_table('notification_dispatches',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('notification_id', sa.BigInteger(), nullable=False),
        sa.Column('channel', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('provider_message_id', sa.String(length=255), nullable=True),
        sa.Column('provider_name', sa.String(length=50), nullable=True),
        sa.Column('rendered_content', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('delivered_at', sa.DateTime(), nullable=True),
        sa.Column('failed_at', sa.DateTime(), nullable=True),
        sa.Column('failure_reason', sa.String(length=500), nullable=True),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('next_retry_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['notification_id'], ['notifications.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('notification_id', 'channel', name='uq_dispatch_notification_channel')
    )
    op.create_index('ix_dispatch_status_retry', 'notification_dispatches', ['status', 'next_retry_at'], unique=False)
    op.create_index(op.f('ix_notification_dispatches_notification_id'), 'notification_dispatches', ['notification_id'], unique=False)
    op.create_index(op.f('ix_notification_dispatches_provider_message_id'), 'notification_dispatches', ['provider_message_id'], unique=False)

    # notification_templates
    op.create_table('notification_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('channel', sa.String(length=20), nullable=False),
        sa.Column('language', sa.String(length=10), nullable=False, server_default='en'),
        sa.Column('subject', sa.String(length=255), nullable=True),
        sa.Column('body_template', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_by', sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_type', 'channel', 'language', name='uq_template_event_channel_lang')
    )

    # notification_preferences
    op.create_table('notification_preferences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('sms_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('whatsapp_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('push_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('email_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'category', name='uq_pref_user_category')
    )

    # scheduled_notifications
    op.create_table('scheduled_notifications',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('fire_at', sa.DateTime(), nullable=False),
        sa.Column('idempotency_key', sa.String(length=255), nullable=False),
        sa.Column('fired_at', sa.DateTime(), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key')
    )
    op.create_index('ix_scheduled_fire_at_fired', 'scheduled_notifications', ['fire_at', 'fired_at'], unique=False)
    op.create_index(op.f('ix_scheduled_notifications_fire_at'), 'scheduled_notifications', ['fire_at'], unique=False)
    op.create_index(op.f('ix_scheduled_notifications_user_id'), 'scheduled_notifications', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_scheduled_notifications_user_id'), table_name='scheduled_notifications')
    op.drop_index(op.f('ix_scheduled_notifications_fire_at'), table_name='scheduled_notifications')
    op.drop_index('ix_scheduled_fire_at_fired', table_name='scheduled_notifications')
    op.drop_table('scheduled_notifications')
    op.drop_table('notification_preferences')
    op.drop_table('notification_templates')
    op.drop_index(op.f('ix_notification_dispatches_provider_message_id'), table_name='notification_dispatches')
    op.drop_index(op.f('ix_notification_dispatches_notification_id'), table_name='notification_dispatches')
    op.drop_index('ix_dispatch_status_retry', table_name='notification_dispatches')
    op.drop_table('notification_dispatches')
    op.drop_index('ix_notifications_user_created', table_name='notifications')
    op.drop_index('ix_notifications_status', table_name='notifications')
    op.drop_index('ix_notifications_source_event', table_name='notifications')
    op.drop_table('notifications')
