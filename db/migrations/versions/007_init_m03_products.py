"""Init M03 products

Revision ID: 007_init_m03_products
Revises: 006_init_m06_payments
Create Date: 2026-04-08 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "007_init_m03_products"
down_revision: Union[str, None] = "006_init_m06_payments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Merchants table
    op.create_table(
        "merchants",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=True),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("platform_type", sa.String(length=30), nullable=True),
        sa.Column("checkout_success_rate", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("bot_detection_level", sa.String(length=20), nullable=False, server_default=sa.text("'low'")),
        sa.Column("has_captcha", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("captcha_type", sa.String(length=30), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("scrape_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("domain"),
        sa.UniqueConstraint("uuid"),
    )

    # 2. Products table with Full-Text Search
    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("merchant_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("title_urdu", sa.String(length=255), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("platform", sa.String(length=30), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default=sa.text("'PKR'")),
        sa.Column("cost_price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("sale_price", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("stock_status", sa.String(length=20), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("in_stock", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("primary_image_s3", sa.String(length=512), nullable=True),
        sa.Column("is_prohibited", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("prohibition_reason", sa.String(length=100), nullable=True),
        sa.Column("extraction_method", sa.String(length=30), nullable=True),
        sa.Column("extraction_confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    
    # Add TSVECTOR for full-text search
    op.execute("ALTER TABLE products ADD COLUMN search_vector tsvector")
    op.execute("CREATE INDEX ix_products_search_vector ON products USING GIN(search_vector)")
    
    # Trigger to update search_vector
    op.execute("""
        CREATE FUNCTION products_search_trigger() RETURNS trigger AS $$
        begin
          new.search_vector :=
            setweight(to_tsvector('english', coalesce(new.name,'')), 'A');
          return new;
        end
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER tsvectorupdate BEFORE INSERT OR UPDATE
        ON products FOR EACH ROW EXECUTE FUNCTION products_search_trigger();
    """)

    op.create_index("ix_products_merchant_id", "products", ["merchant_id"], unique=False)
    op.create_index("ix_products_platform", "products", ["platform"], unique=False)
    op.create_index("ix_products_extraction_method", "products", ["extraction_method"], unique=False)

    # 3. Scraping Jobs
    op.create_table(
        "scraping_jobs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("product_id", sa.BigInteger(), nullable=True),
        sa.Column("input_url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("platform_detected", sa.String(length=30), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("attempt_number", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column("max_attempts", sa.SmallInteger(), nullable=False, server_default=sa.text("3")),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("queued_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_scraping_jobs_order_created", "scraping_jobs", ["order_id", "created_at"], unique=False)
    op.create_index("ix_scraping_jobs_status_created", "scraping_jobs", ["status", "created_at"], unique=False)
    op.create_index("ix_scraping_jobs_user_status", "scraping_jobs", ["user_id", "status"], unique=False)

    # 4. Prohibited Categories
    op.create_table(
        "prohibited_categories",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("category_name", sa.String(length=100), nullable=False),
        sa.Column("keywords", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("shariah_basis", sa.Text(), nullable=True),
        sa.Column("added_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category_name"),
    )

    # 5. Prohibited Item Logs
    op.create_table(
        "prohibited_item_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("product_id", sa.BigInteger(), nullable=True),
        sa.Column("raw_url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("detected_category", sa.String(length=100), nullable=False),
        sa.Column("detected_keyword", sa.String(length=100), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_prohibited_item_logs_created_at", "prohibited_item_logs", ["created_at"], unique=False)
    op.create_index("ix_prohibited_item_logs_user_id", "prohibited_item_logs", ["user_id"], unique=False)
    
    # 6. Link Orders to Products
    op.add_column("orders", sa.Column("product_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key("fk_orders_product_id", "orders", "products", ["product_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_index("ix_prohibited_item_logs_user_id", table_name="prohibited_item_logs")
    op.drop_index("ix_prohibited_item_logs_created_at", table_name="prohibited_item_logs")
    op.drop_table("prohibited_item_logs")
    op.drop_table("prohibited_categories")
    op.drop_index("ix_scraping_jobs_user_status", table_name="scraping_jobs")
    op.drop_index("ix_scraping_jobs_status_created", table_name="scraping_jobs")
    op.drop_index("ix_scraping_jobs_order_created", table_name="scraping_jobs")
    op.drop_table("scraping_jobs")
    
    op.execute("DROP TRIGGER tsvectorupdate ON products")
    op.execute("DROP FUNCTION products_search_trigger")
    op.drop_index("ix_products_search_vector", table_name="products")
    
    op.drop_index("ix_products_extraction_method", table_name="products")
    op.drop_index("ix_products_platform", table_name="products")
    op.drop_index("ix_products_merchant_id", table_name="products")
    op.drop_table("products")
    op.drop_table("merchants")
    
    # Remove Link
    op.drop_constraint("fk_orders_product_id", "orders", type_="foreignkey")
    op.drop_column("orders", "product_id")