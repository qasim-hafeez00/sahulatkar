"""Add partner/commission fields to merchants + onboarding/commission/payout tables

Revision ID: 065
Revises: 064
Create Date: 2026-07-04 00:00:00.000000

Module 10 (Merchants) — the existing `merchants` table models the
scraping/checkout side of a merchant (bot detection, captcha, scrape config).
This migration adds the commercial-partnership fields the admin Merchants
module needs (partner type, commission terms, onboarding status) without
touching the existing scraping-related columns, plus three new tables for
onboarding applications, commission accrual, and payouts.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '065'
down_revision: Union[str, None] = '064'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("merchants", sa.Column("partner_type", sa.String(length=30), nullable=True))
    op.add_column("merchants", sa.Column("commission_rate_pct", sa.Numeric(5, 2), nullable=True))
    op.add_column("merchants", sa.Column("payment_terms_days", sa.SmallInteger(), nullable=True))
    op.add_column("merchants", sa.Column("min_volume_commitment_pkr", sa.Numeric(14, 2), nullable=True))
    op.add_column(
        "merchants",
        sa.Column("onboarding_status", sa.String(length=20), nullable=False, server_default="not_started"),
    )
    op.create_check_constraint(
        "chk_merchants_partner_type",
        "merchants",
        "partner_type IN ('direct_integration','affiliate','scraped_only') OR partner_type IS NULL",
    )
    op.create_check_constraint(
        "chk_merchants_onboarding_status",
        "merchants",
        "onboarding_status IN ('not_started','in_review','approved','rejected','active')",
    )

    op.create_table(
        "merchant_onboarding_applications",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("merchant_name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("contact_name", sa.String(length=255), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=20), nullable=True),
        sa.Column("proposed_partner_type", sa.String(length=30), nullable=True),
        sa.Column("proposed_commission_rate_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("merchant_id", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_by", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending','in_review','approved','rejected')"),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index(
        "ix_merchant_onboarding_applications_status",
        "merchant_onboarding_applications",
        ["status"],
        unique=False,
    )

    op.create_table(
        "merchant_commission_accruals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("merchant_id", sa.BigInteger(), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("order_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("commission_rate_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("commission_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="accrued"),
        sa.Column("payout_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('accrued','paid_out','reversed')"),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"], ondelete="CASCADE"),
        # No FK to orders — it's a partitioned table without a plain-id unique
        # constraint, consistent with this codebase's existing convention.
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_merchant_commission_accruals_merchant_status",
        "merchant_commission_accruals",
        ["merchant_id", "status"],
        unique=False,
    )

    op.create_table(
        "merchant_payouts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("merchant_id", sa.BigInteger(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("reference_number", sa.String(length=100), nullable=True),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("initiated_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending','processing','paid','failed')"),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["initiated_by"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )

    for table in ("merchant_onboarding_applications", "merchant_commission_accruals", "merchant_payouts"):
        for role in ("sk_app", "sk_admin"):
            op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {role}")
    for role in ("sk_app", "sk_admin"):
        op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}")


def downgrade() -> None:
    op.drop_table("merchant_payouts")
    op.drop_table("merchant_commission_accruals")
    op.drop_table("merchant_onboarding_applications")
    op.drop_constraint("chk_merchants_onboarding_status", "merchants", type_="check")
    op.drop_constraint("chk_merchants_partner_type", "merchants", type_="check")
    op.drop_column("merchants", "onboarding_status")
    op.drop_column("merchants", "min_volume_commitment_pkr")
    op.drop_column("merchants", "payment_terms_days")
    op.drop_column("merchants", "commission_rate_pct")
    op.drop_column("merchants", "partner_type")
