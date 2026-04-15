"""Marketing Growth

Revision ID: 022_marketing_growth
Revises: 021_support_communications
Create Date: 2026-04-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '022_marketing_growth'
down_revision: Union[str, None] = '021_support_communications'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "referrals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("referrer_user_id", sa.BigInteger(), nullable=False),
        sa.Column("referred_user_id", sa.BigInteger(), nullable=False),
        sa.Column("referral_code", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default='pending'),
        sa.Column("referrer_reward_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("referred_reward_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("reward_type", sa.String(length=30), nullable=True),
        sa.Column("reward_paid_at", sa.DateTime(), nullable=True),
        sa.Column("first_order_id", sa.BigInteger(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending','registered','kyc_complete','first_order_placed','reward_paid','expired')"),
        sa.CheckConstraint("reward_type IN ('credit_limit_bonus','cashback','fee_waiver')"),
        sa.ForeignKeyConstraint(["first_order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["referred_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["referrer_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("referrer_user_id", "referred_user_id"),
    )
    op.create_index("ix_referrals_referrer_user_id_status", "referrals", ["referrer_user_id", "status"], unique=False)
    op.create_index("ix_referrals_referral_code", "referrals", ["referral_code"], unique=False)

    op.create_table(
        "promotional_codes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("promo_type", sa.String(length=30), nullable=False),
        sa.Column("discount_value", sa.Numeric(10, 2), nullable=True),
        sa.Column("discount_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("min_order_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("max_discount_cap", sa.Numeric(10, 2), nullable=True),
        sa.Column("usage_limit_total", sa.Integer(), nullable=True),
        sa.Column("usage_limit_per_user", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column("times_used", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("valid_from", sa.DateTime(), nullable=False),
        sa.Column("valid_until", sa.DateTime(), nullable=False),
        sa.Column("applicable_cities", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("promo_type IN ('fee_waiver','credit_bonus','cashback_pct','cashback_flat','free_delivery')"),
        sa.CheckConstraint("discount_pct BETWEEN 0 AND 100"),
        sa.ForeignKeyConstraint(["created_by"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.UniqueConstraint("uuid"),
    )

    op.create_table(
        "promo_code_usage",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("promo_code_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("discount_applied", sa.Numeric(10, 2), nullable=False),
        sa.Column("used_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["promo_code_id"], ["promotional_codes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("promo_code_id", "order_id"),
    )
    op.create_index("ix_promo_code_usage_user_id_promo_code_id", "promo_code_usage", ["user_id", "promo_code_id"], unique=False)

    op.create_table(
        "marketing_campaigns",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("channel", sa.String(length=30), nullable=False),
        sa.Column("target_segment", sa.Text(), nullable=True),
        sa.Column("budget", sa.Numeric(14, 2), nullable=True),
        sa.Column("spend", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default='draft'),
        sa.Column("utm_parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("channel IN ('meta_ads','google','sms_blast','influencer','email','tiktok')"),
        sa.CheckConstraint("status IN ('draft','active','paused','completed')"),
        sa.ForeignKeyConstraint(["created_by"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )

    op.create_table(
        "campaign_metrics",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("registrations", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("first_orders", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("cac", sa.Numeric(10, 2), nullable=True),
        sa.Column("roi", sa.Numeric(8, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["marketing_campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "date"),
    )

    op.create_table(
        "user_acquisition_attribution",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("first_touch_source", sa.String(length=50), nullable=True),
        sa.Column("first_touch_medium", sa.String(length=50), nullable=True),
        sa.Column("last_touch_source", sa.String(length=50), nullable=True),
        sa.Column("last_touch_medium", sa.String(length=50), nullable=True),
        sa.Column("utm_source", sa.String(length=100), nullable=True),
        sa.Column("utm_medium", sa.String(length=100), nullable=True),
        sa.Column("utm_campaign", sa.String(length=100), nullable=True),
        sa.Column("utm_content", sa.String(length=100), nullable=True),
        sa.Column("campaign_id", sa.BigInteger(), nullable=True),
        sa.Column("attributed_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["marketing_campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    op.create_table(
        "ab_test_experiments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("experiment_name", sa.String(length=255), nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=True),
        sa.Column("variants", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metric_to_optimize", sa.String(length=100), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("winner_variant", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default='draft'),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('draft','running','paused','completed')"),
        sa.ForeignKeyConstraint(["created_by"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("experiment_name"),
        sa.UniqueConstraint("uuid"),
    )

    op.create_table(
        "ab_test_assignments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("experiment_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("variant_name", sa.String(length=50), nullable=False),
        sa.Column("assigned_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["ab_test_experiments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("experiment_id", "user_id"),
    )
    op.create_index("ix_ab_test_assignments_experiment_id_variant_name", "ab_test_assignments", ["experiment_id", "variant_name"], unique=False)

    op.create_table(
        "conversion_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("session_id", sa.String(length=100), nullable=True),
        sa.Column("event_name", sa.String(length=100), nullable=False),
        sa.Column("event_properties", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversion_events_user_id_event_name_created_at", "conversion_events", ["user_id", "event_name", sa.text("created_at DESC")], unique=False)


def downgrade() -> None:
    op.drop_table("conversion_events")
    op.drop_table("ab_test_assignments")
    op.drop_table("ab_test_experiments")
    op.drop_table("user_acquisition_attribution")
    op.drop_table("campaign_metrics")
    op.drop_table("marketing_campaigns")
    op.drop_table("promo_code_usage")
    op.drop_table("promotional_codes")
    op.drop_table("referrals")
