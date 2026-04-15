"""Product Merchant Remaining

Revision ID: 015_product_merchant_remaining
Revises: 014_credit_risk_remaining
Create Date: 2026-04-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '015_product_merchant_remaining'
down_revision: Union[str, None] = '014_credit_risk_remaining'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "product_variants",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("variant_type", sa.String(length=50), nullable=False),
        sa.Column("variant_value", sa.String(length=100), nullable=False),
        sa.Column("price_delta", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("stock_status", sa.String(length=20), nullable=False, server_default='unknown'),
        sa.Column("sku", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("stock_status IN ('in_stock','out_of_stock','limited','unknown')"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_product_variants_product_id", "product_variants", ["product_id"], unique=False)

    op.create_table(
        "product_prices_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("price", sa.Numeric(14, 2), nullable=False),
        sa.Column("original_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default='PKR'),
        sa.Column("recorded_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_prices_history_product_id_recorded_at", "product_prices_history", ["product_id", sa.text("recorded_at DESC")], unique=False)

    op.create_table(
        "product_images",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("image_url", sa.String(length=2048), nullable=True),
        sa.Column("s3_cached_url", sa.String(length=512), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_images_product_id_is_primary", "product_images", ["product_id", "is_primary"], unique=False)

    op.create_table(
        "merchant_performance_metrics",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("merchant_id", sa.BigInteger(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("success_rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("avg_checkout_sec", sa.Integer(), nullable=True),
        sa.Column("captcha_failure_rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("ban_rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("order_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("merchant_id", "date"),
    )
    op.create_index("ix_merchant_performance_metrics_merchant_id_date", "merchant_performance_metrics", ["merchant_id", sa.text("date DESC")], unique=False)

    op.create_table(
        "product_availability_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column("price", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default='PKR'),
        sa.Column("checked_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_availability_history_product_id_checked_at", "product_availability_history", ["product_id", sa.text("checked_at DESC")], unique=False)


def downgrade() -> None:
    op.drop_table("product_availability_history")
    op.drop_table("merchant_performance_metrics")
    op.drop_table("product_images")
    op.drop_table("product_prices_history")
    op.drop_table("product_variants")
