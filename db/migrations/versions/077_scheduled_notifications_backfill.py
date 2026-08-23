"""Backfill scheduled_notifications table

Revision ID: 077
Revises: 076
Create Date: 2026-07-30 00:00:00.000001

Migration 049 (`op.create_table('scheduled_notifications', ...)`) is recorded as applied
(alembic_version reaches 049 and its four sibling tables — notifications,
notification_dispatches, notification_templates, notification_preferences — exist), but
`scheduled_notifications` itself is absent from the database. `run_scheduled_worker` in
notification-service has been crash-looping every interval on `UndefinedTableError` as a
result. Using `IF NOT EXISTS` here so this is safe to apply regardless of environment.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '077'
down_revision: Union[str, None] = '076'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = 'scheduled_notifications'"
    )).scalar()
    if exists:
        return

    op.create_table(
        'scheduled_notifications',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('fire_at', sa.DateTime(), nullable=False),
        sa.Column('idempotency_key', sa.String(length=255), nullable=False),
        sa.Column('fired_at', sa.DateTime(), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key'),
    )
    op.create_index('ix_scheduled_fire_at_fired', 'scheduled_notifications', ['fire_at', 'fired_at'], unique=False)
    op.create_index(op.f('ix_scheduled_notifications_fire_at'), 'scheduled_notifications', ['fire_at'], unique=False)
    op.create_index(op.f('ix_scheduled_notifications_user_id'), 'scheduled_notifications', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_scheduled_notifications_user_id'), table_name='scheduled_notifications')
    op.drop_index(op.f('ix_scheduled_notifications_fire_at'), table_name='scheduled_notifications')
    op.drop_index('ix_scheduled_fire_at_fired', table_name='scheduled_notifications')
    op.drop_table('scheduled_notifications')
