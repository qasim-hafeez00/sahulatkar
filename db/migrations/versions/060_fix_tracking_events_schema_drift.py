"""Add tracking_events created_at/updated_at

Revision ID: 060
Revises: 059
Create Date: 2026-07-03 00:00:08.000000

TrackingEvent's TimestampMixin expects created_at/updated_at, but the
physical (partitioned) table only has `received_at`. event_time is left as
TIMESTAMP WITHOUT TIME ZONE — it's the table's RANGE partition key, and
Postgres refuses to ALTER the type of a partition key column; the model is
annotated to require naive datetimes from callers instead.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '060'
down_revision: Union[str, None] = '059'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tracking_events", sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.add_column("tracking_events", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade() -> None:
    op.drop_column("tracking_events", "updated_at")
    op.drop_column("tracking_events", "created_at")
