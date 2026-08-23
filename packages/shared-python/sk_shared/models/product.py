from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Numeric, SmallInteger, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDMixin, SoftDeleteMixin


class Merchant(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "merchants"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True)
    platform_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    checkout_success_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    bot_detection_level: Mapped[str] = mapped_column(String(20), nullable=False, default="low")
    has_captcha: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    captcha_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    scrape_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Commercial partnership fields (Module 10 — Admin Merchants)
    partner_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    commission_rate_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    payment_terms_days: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    min_volume_commitment_pkr: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    onboarding_status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_started")

    products: Mapped[list["Product"]] = relationship("Product", back_populates="merchant")


class Product(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    merchant_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("merchants.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    title_urdu: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    platform: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="PKR")
    cost_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    sale_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    stock_status: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    primary_image_s3: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    secondary_images: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    is_prohibited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    prohibition_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    extraction_method: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    extraction_confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3), nullable=True)
    brand: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ships_to_pakistan: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    variants: Mapped[Optional[list[dict]]] = mapped_column(JSON, nullable=True)
    shariah_category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Use a generic JSON for search_vector fallback on SQLite, real TSVECTOR on Postgres
    search_vector: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    merchant: Mapped[Optional["Merchant"]] = relationship("Merchant", back_populates="products")
    scraping_jobs: Mapped[list["ScrapingJob"]] = relationship("ScrapingJob", back_populates="product")

    __table_args__ = (
        Index("ix_products_merchant_id", "merchant_id"),
        Index("ix_products_platform", "platform"),
        Index("ix_products_extraction_method", "extraction_method"),
        Index("ix_products_search_vector", "search_vector", postgresql_using="gin"),
    )


class ScrapingJob(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "scraping_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    product_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    input_url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    platform_detected: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    attempt_number: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    max_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=3)
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    product: Mapped[Optional["Product"]] = relationship("Product", back_populates="scraping_jobs")

    __table_args__ = (
        Index("ix_scraping_jobs_order_created", "order_id", "created_at"),
        Index("ix_scraping_jobs_user_status", "user_id", "status"),
        Index("ix_scraping_jobs_status_created", "status", "created_at"),
    )


class ProhibitedCategory(Base, TimestampMixin):
    __tablename__ = "prohibited_categories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    category_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    shariah_basis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)


class ProhibitedItemLog(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "prohibited_item_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    product_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    raw_url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    detected_category: Mapped[str] = mapped_column(String(100), nullable=False)
    detected_keyword: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    decision_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    product: Mapped[Optional["Product"]] = relationship("Product")

    __table_args__ = (
        Index("ix_prohibited_item_logs_user_id", "user_id"),
        Index("ix_prohibited_item_logs_created_at", "created_at"),
    )
