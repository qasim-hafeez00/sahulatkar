"""Delivery Remaining

Revision ID: 018_delivery_remaining
Revises: 017_payment_remaining
Create Date: 2026-04-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '018_delivery_remaining'
down_revision: Union[str, None] = '017_payment_remaining'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Update shipments
    op.add_column('shipments', sa.Column('recipient_name', sa.String(length=100), nullable=True))
    op.add_column('shipments', sa.Column('recipient_phone', sa.String(length=20), nullable=True))
    op.add_column('shipments', sa.Column('weight_kg', sa.Numeric(6, 2), nullable=True))
    op.add_column('shipments', sa.Column('shipping_cost', sa.Numeric(10, 2), nullable=True))
    op.add_column('shipments', sa.Column('is_cod', sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column('shipments', sa.Column('cod_amount', sa.Numeric(10, 2), nullable=True))
    op.add_column('shipments', sa.Column('delivery_address_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('shipments', sa.Column('courier_tracking_url', sa.String(length=2048), nullable=True))

    op.create_table(
        "delivery_attempts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("shipment_id", sa.BigInteger(), nullable=False),
        sa.Column("attempt_number", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column("attempted_at", sa.DateTime(), nullable=False),
        sa.Column("outcome", sa.String(length=30), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("outcome IN ('delivered','failed','refused','rescheduled')"),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_delivery_attempts_shipment_id_attempted_at", "delivery_attempts", ["shipment_id", sa.text("attempted_at DESC")], unique=False)

    op.create_table(
        "delivery_proofs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("shipment_id", sa.BigInteger(), nullable=False),
        sa.Column("proof_type", sa.String(length=30), nullable=False),
        sa.Column("proof_s3_url", sa.String(length=512), nullable=True),
        sa.Column("recipient_name", sa.String(length=100), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("proof_type IN ('photo','signature','otp_confirmation')"),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_delivery_proofs_shipment_id", "delivery_proofs", ["shipment_id"], unique=False)

    op.create_table(
        "return_shipments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("original_shipment_id", sa.BigInteger(), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("courier_id", sa.BigInteger(), nullable=True),
        sa.Column("tracking_number", sa.String(length=100), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default='initiated'),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('initiated','in_transit','received','completed')"),
        sa.ForeignKeyConstraint(["courier_id"], ["couriers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["original_shipment_id"], ["shipments.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_return_shipments_original_shipment_id", "return_shipments", ["original_shipment_id"], unique=False)
    op.create_index("ix_return_shipments_order_id", "return_shipments", ["order_id"], unique=False)

    op.create_table(
        "courier_performance_metrics",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("courier_id", sa.BigInteger(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("on_time_rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("delivery_success_rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("avg_transit_days", sa.Numeric(4, 1), nullable=True),
        sa.Column("complaint_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("order_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["courier_id"], ["couriers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("courier_id", "date"),
    )
    op.create_index("ix_courier_performance_metrics_courier_id_date", "courier_performance_metrics", ["courier_id", sa.text("date DESC")], unique=False)


def downgrade() -> None:
    op.drop_table("courier_performance_metrics")
    op.drop_table("return_shipments")
    op.drop_table("delivery_proofs")
    op.drop_table("delivery_attempts")

    op.drop_column('shipments', 'courier_tracking_url')
    op.drop_column('shipments', 'delivery_address_snapshot')
    op.drop_column('shipments', 'cod_amount')
    op.drop_column('shipments', 'is_cod')
    op.drop_column('shipments', 'shipping_cost')
    op.drop_column('shipments', 'weight_kg')
    op.drop_column('shipments', 'recipient_phone')
    op.drop_column('shipments', 'recipient_name')
