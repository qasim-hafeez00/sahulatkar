"""Add outbox_events table for payment-orchestrator

Revision ID: 075
Revises: 074
Create Date: 2026-07-30 00:00:00.000000

`apps/payment-orchestrator/src/models/outbox.py` defines `OutboxEvent` (used by
`src/workers/outbox_publisher.py`) against the shared declarative `Base`, but the model
lives in the app package rather than `sk_shared.models`, so it was never picked up by
`db/migrations/env.py`'s `from sk_shared.models import *` and no migration ever created
the table — the publisher worker has been crash-looping on `UndefinedTableError` since
the service was first run against a migrated database.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '075'
down_revision: Union[str, None] = '074'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'outbox_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('uuid', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('event_name', sa.String(length=100), nullable=False),
        sa.Column('payload', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid'),
    )
    op.create_index(
        'ix_outbox_events_status_retry_count',
        'outbox_events',
        ['status', 'retry_count'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_outbox_events_status_retry_count', table_name='outbox_events')
    op.drop_table('outbox_events')
