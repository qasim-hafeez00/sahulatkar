"""Add shariah_board_approvals and processed_webhook_events tables

Revision ID: 087
Revises: 086
Create Date: 2026-08-28 00:00:00.000000

Two independent compliance/reliability fixes from the 2026-08 production
gaps report, bundled into one migration since both are small, additive
table creations with no interaction between them:

1. shariah_board_approvals: backs MurabahaContract.validated_by_shariah_board,
   which was previously hardcoded True on every generated contract with no
   approval record anywhere in the codebase (HIGH finding). An admin now
   records which contract template_version the Shariah board has actually
   approved here; ContractGeneratorService.generate_murabaha checks the
   template_version it's about to stamp against this table before setting
   the flag.

2. processed_webhook_events: a durable second layer for inbound payment
   webhook dedup (api/v1/webhooks.py's _enqueue_webhook), which previously
   relied solely on a 24h Redis SETNX marker with no DB fallback -- a
   retried webhook arriving while Redis is unavailable (or after the key
   was evicted) would be reprocessed with nothing to catch it (MEDIUM
   finding).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '087'
down_revision: Union[str, None] = '086'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shariah_board_approvals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("template_version", sa.String(length=10), nullable=False),
        sa.Column("approved_by", sa.String(length=200), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_version"),
    )

    op.create_table(
        "processed_webhook_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("gateway", sa.String(length=50), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_processed_webhook_events_processed_at",
        "processed_webhook_events",
        ["processed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_processed_webhook_events_processed_at", table_name="processed_webhook_events")
    op.drop_table("processed_webhook_events")
    op.drop_table("shariah_board_approvals")
