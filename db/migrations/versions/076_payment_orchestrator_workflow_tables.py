"""Add payment-orchestrator workflow tables

Revision ID: 076
Revises: 075
Create Date: 2026-07-30 00:00:00.000000

Same gap as 075: `payment_workflows`/`payment_events` (models/payment_workflow.py),
`payment_mandates` (models/payment_mandate.py), and `refund_workflows`
(models/refund_workflow.py) are declared against the shared `Base` from app-local
model modules under `apps/payment-orchestrator/src/models/`, so `db/migrations/env.py`
(which only imports `sk_shared.models`) never saw them and no migration created them.
`PaymentSessionExpiryWorker` has been crash-looping on `payment_workflows` being
undefined since the service started against a migrated database.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '076'
down_revision: Union[str, None] = '075'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'payment_workflows',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('uuid', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('order_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('idempotency_key', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='initiated'),
        sa.Column('gateway', sa.String(length=20), nullable=False),
        sa.Column('gateway_session_id', sa.String(length=255), nullable=True),
        sa.Column('amount_pkr', sa.Numeric(14, 2), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='PKR'),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('session_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid'),
        sa.UniqueConstraint('idempotency_key'),
    )
    op.create_index(
        'ix_payment_workflows_status_expires',
        'payment_workflows',
        ['status', 'session_expires_at'],
        unique=False,
    )
    op.create_index('ix_payment_workflows_order_id', 'payment_workflows', ['order_id'], unique=False)

    op.create_table(
        'payment_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('payment_workflow_id', sa.BigInteger(), nullable=False),
        sa.Column('from_status', sa.String(length=20), nullable=False),
        sa.Column('to_status', sa.String(length=20), nullable=False),
        sa.Column('trigger', sa.String(length=100), nullable=False),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['payment_workflow_id'], ['payment_workflows.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_payment_events_workflow_id', 'payment_events', ['payment_workflow_id'], unique=False)

    op.create_table(
        'payment_mandates',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('uuid', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('gateway', sa.String(length=20), nullable=False),
        sa.Column('mandate_reference', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('max_amount_per_txn', sa.Numeric(14, 2), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='PKR'),
        sa.Column('payer_identifier', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid'),
        sa.UniqueConstraint('mandate_reference'),
    )
    op.create_index('ix_payment_mandates_user_id', 'payment_mandates', ['user_id'], unique=False)

    op.create_table(
        'refund_workflows',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('uuid', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('original_payment_workflow_id', sa.BigInteger(), nullable=False),
        sa.Column('order_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('refund_reference', sa.String(length=255), nullable=False),
        sa.Column('amount_pkr', sa.Numeric(14, 2), nullable=False),
        sa.Column('reason', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='initiated'),
        sa.Column('gateway', sa.String(length=20), nullable=False),
        sa.Column('gateway_refund_id', sa.String(length=255), nullable=True),
        sa.Column('initiated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('settled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['original_payment_workflow_id'], ['payment_workflows.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid'),
        sa.UniqueConstraint('refund_reference'),
    )
    op.create_index('ix_refund_workflows_order_id', 'refund_workflows', ['order_id'], unique=False)


def downgrade() -> None:
    op.drop_table('refund_workflows')
    op.drop_table('payment_mandates')
    op.drop_table('payment_events')
    op.drop_table('payment_workflows')
