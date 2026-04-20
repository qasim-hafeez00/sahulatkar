"""Product service hardening: canonical URL uniqueness + price history

Revision ID: 044_product_service_price_history_and_canonical_unique
Revises: 043_add_orders_installment_count
Create Date: 2026-04-21 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "044_product_service_price_history_and_canonical_unique"
down_revision: Union[str, None] = "043_add_orders_installment_count"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "product_price_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("old_price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("new_price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("changed_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("changed_by_job_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["changed_by_job_id"], ["scraping_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_product_price_history_product_changed",
        "product_price_history",
        ["product_id", "changed_at"],
        unique=False,
    )

    # Enforce one canonical product URL record; NULL values remain unconstrained.
    op.create_unique_constraint("uq_products_canonical_url", "products", ["canonical_url"])


def downgrade() -> None:
    op.drop_constraint("uq_products_canonical_url", "products", type_="unique")
    op.drop_index("ix_product_price_history_product_changed", table_name="product_price_history")
    op.drop_table("product_price_history")
