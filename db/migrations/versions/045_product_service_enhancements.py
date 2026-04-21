"""Product service enhancements: product metadata, lifecycle, and staleness support.

Revision ID: 045_product_service_enhancements
Revises: 044_product_service_price_history_and_canonical_unique
Create Date: 2026-04-21 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "045_product_service_enhancements"
down_revision: Union[str, None] = "044_product_service_price_history_and_canonical_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'active'")
    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS description TEXT")
    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS brand VARCHAR(255)")
    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS ships_to_pakistan BOOLEAN NOT NULL DEFAULT TRUE")
    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS variants JSONB")
    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS secondary_images JSONB")
    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS shariah_category VARCHAR(100)")

    op.create_check_constraint(
        "products_status_check",
        "products",
        "status IN ('active', 'stale', 'prohibited', 'deleted', 'extraction_failed')",
    )

    op.create_index(
        "ix_products_status_updated",
        "products",
        ["status", "updated_at"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_products_variants_gin",
        "products",
        ["variants"],
        unique=False,
        postgresql_using="gin",
        postgresql_where=sa.text("variants IS NOT NULL"),
    )
    op.create_index(
        "ix_products_shariah_category",
        "products",
        ["shariah_category"],
        unique=False,
        postgresql_where=sa.text("shariah_category IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_products_shariah_category", table_name="products")
    op.drop_index("ix_products_variants_gin", table_name="products")
    op.drop_index("ix_products_status_updated", table_name="products")
    op.drop_constraint("products_status_check", "products", type_="check")
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS shariah_category")
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS secondary_images")
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS variants")
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS ships_to_pakistan")
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS brand")
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS description")
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS status")
