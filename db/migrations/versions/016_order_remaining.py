"""Order Remaining

Revision ID: 016_order_remaining
Revises: 015_product_merchant_remaining
Create Date: 2026-04-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '016_order_remaining'
down_revision: Union[str, None] = '015_product_merchant_remaining'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Update orders table
    op.add_column('orders', sa.Column('product_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('orders', sa.Column('selected_variant', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('orders', sa.Column('product_cost', sa.Numeric(14, 2), nullable=True))
    op.add_column('orders', sa.Column('platform_profit', sa.Numeric(14, 2), nullable=True))
    op.add_column('orders', sa.Column('currency', sa.String(length=3), server_default='PKR', nullable=False))
    op.add_column('orders', sa.Column('delivery_address_id', sa.BigInteger(), nullable=True))
    op.add_column('orders', sa.Column('delivery_address_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('orders', sa.Column('risk_assessment_id', sa.BigInteger(), nullable=True))
    op.add_column('orders', sa.Column('down_payment_pct', sa.Numeric(5, 2), nullable=True))
    op.add_column('orders', sa.Column('merchant_order_id', sa.String(length=255), nullable=True))
    op.add_column('orders', sa.Column('merchant_order_url', sa.String(length=2048), nullable=True))
    op.add_column('orders', sa.Column('cancelled_at', sa.DateTime(), nullable=True))
    op.add_column('orders', sa.Column('cancel_reason', sa.String(length=100), nullable=True))
    op.add_column('orders', sa.Column('cancelled_by', sa.String(length=20), nullable=True))
    op.add_column('orders', sa.Column('admin_notes', sa.Text(), nullable=True))
    op.add_column('orders', sa.Column('order_number', sa.String(length=30), nullable=True))

    op.create_table(
        "order_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=True),
        sa.Column("variant_id", sa.BigInteger(), nullable=True),
        sa.Column("quantity", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("subtotal", sa.Numeric(14, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"], unique=False)

    op.create_table(
        "order_addresses",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("address_type", sa.String(length=20), nullable=False),
        sa.Column("address_line_1", sa.String(length=255), nullable=False),
        sa.Column("address_line_2", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("province", sa.String(length=50), nullable=False),
        sa.Column("postal_code", sa.String(length=10), nullable=True),
        sa.Column("country", sa.String(length=50), nullable=False, server_default='Pakistan'),
        sa.Column("recipient_name", sa.String(length=100), nullable=True),
        sa.Column("recipient_phone", sa.String(length=20), nullable=True),
        sa.Column("latitude", sa.Numeric(10, 8), nullable=True),
        sa.Column("longitude", sa.Numeric(11, 8), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("address_type IN ('delivery','billing')"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_order_addresses_order_id", "order_addresses", ["order_id"], unique=False)

    op.create_table(
        "order_cancellations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("reason_code", sa.String(length=50), nullable=False),
        sa.Column("reason_detail", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.String(length=20), nullable=False),
        sa.Column("approved_by", sa.BigInteger(), nullable=True),
        sa.Column("refund_initiated_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("requested_by IN ('user','admin','system')"),
        sa.ForeignKeyConstraint(["approved_by"], ["admin_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_order_cancellations_order_id", "order_cancellations", ["order_id"], unique=False)

    op.create_table(
        "order_returns",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("reason_code", sa.String(length=50), nullable=False),
        sa.Column("return_status", sa.String(length=30), nullable=False, server_default='requested'),
        sa.Column("return_shipment_id", sa.BigInteger(), nullable=True),
        sa.Column("refund_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("return_status IN ('requested','approved','in_transit','received','refunded','rejected')"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_order_returns_order_id", "order_returns", ["order_id"], unique=False)

    op.create_table(
        "order_notes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("note_text", sa.Text(), nullable=False),
        sa.Column("created_by_admin_id", sa.BigInteger(), nullable=True),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_admin_id"], ["admin_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_order_notes_order_id_created_at", "order_notes", ["order_id", sa.text("created_at DESC")], unique=False)


def downgrade() -> None:
    op.drop_table("order_notes")
    op.drop_table("order_returns")
    op.drop_table("order_cancellations")
    op.drop_table("order_addresses")
    op.drop_table("order_items")

    op.drop_column('orders', 'order_number')
    op.drop_column('orders', 'admin_notes')
    op.drop_column('orders', 'cancelled_by')
    op.drop_column('orders', 'cancel_reason')
    op.drop_column('orders', 'cancelled_at')
    op.drop_column('orders', 'merchant_order_url')
    op.drop_column('orders', 'merchant_order_id')
    op.drop_column('orders', 'down_payment_pct')
    op.drop_column('orders', 'risk_assessment_id')
    op.drop_column('orders', 'delivery_address_snapshot')
    op.drop_column('orders', 'delivery_address_id')
    op.drop_column('orders', 'currency')
    op.drop_column('orders', 'platform_profit')
    op.drop_column('orders', 'product_cost')
    op.drop_column('orders', 'selected_variant')
    op.drop_column('orders', 'product_snapshot')
