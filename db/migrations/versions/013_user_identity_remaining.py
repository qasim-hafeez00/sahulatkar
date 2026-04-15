"""User Identity Remaining

Revision ID: 013_user_identity_remaining
Revises: 012_fix_migration_conflicts
Create Date: 2026-04-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '013_user_identity_remaining'
down_revision: Union[str, None] = '012_fix_migration_conflicts'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Drop wrong payment_methods table from 006 with CASCADE to handle foreign keys
    op.execute("DROP TABLE IF EXISTS payment_methods CASCADE")

    op.create_table(
        "user_addresses",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("label", sa.String(length=50), nullable=True),
        sa.Column("address_line_1", sa.String(length=255), nullable=False),
        sa.Column("address_line_2", sa.String(length=255), nullable=True),
        sa.Column("area", sa.String(length=100), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("province", sa.String(length=50), nullable=False),
        sa.Column("postal_code", sa.String(length=10), nullable=True),
        sa.Column("country", sa.String(length=50), nullable=False, server_default='Pakistan'),
        sa.Column("latitude", sa.Numeric(10, 8), nullable=True),
        sa.Column("longitude", sa.Numeric(11, 8), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("province IN ('Sindh','Punjab','KPK','Balochistan','Gilgit-Baltistan','AJK','ICT')"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_user_addresses_user_id", "user_addresses", ["user_id"], unique=False)

    op.create_table(
        "user_payment_methods",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("wallet_number", sa.String(length=20), nullable=True),
        sa.Column("wallet_name", sa.String(length=100), nullable=True),
        sa.Column("bank_name", sa.String(length=100), nullable=True),
        sa.Column("iban_encrypted", postgresql.BYTEA(), nullable=True),
        sa.Column("account_title", sa.String(length=100), nullable=True),
        sa.Column("card_last_four", sa.String(length=4), nullable=True),
        sa.Column("card_brand", sa.String(length=20), nullable=True),
        sa.Column("card_expiry_month", sa.SmallInteger(), nullable=True),
        sa.Column("card_expiry_year", sa.SmallInteger(), nullable=True),
        sa.Column("card_token", sa.String(length=255), nullable=True),
        sa.Column("raast_id", sa.String(length=30), nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("type IN ('jazzcash','easypaisa','bank_account','debit_card','sadapay','nayapay','raast')"),
        sa.CheckConstraint("card_expiry_month BETWEEN 1 AND 12"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_user_payment_methods_user_id", "user_payment_methods", ["user_id"], unique=False)
    op.create_index("ix_user_payment_methods_type", "user_payment_methods", ["type"], unique=False)

    op.create_table(
        "user_bank_accounts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("bank_name", sa.String(length=100), nullable=False),
        sa.Column("iban_encrypted", postgresql.BYTEA(), nullable=False),
        sa.Column("account_title", sa.String(length=100), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_user_bank_accounts_user_id", "user_bank_accounts", ["user_id"], unique=False)

    op.create_table(
        "user_consent_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("consent_type", sa.String(length=50), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("consented_at", sa.DateTime(), nullable=False),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("decision IN ('accepted','withdrawn')"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_user_consent_records_user_id_type", "user_consent_records", ["user_id", "consent_type"], unique=False)

    op.create_table(
        "user_activity_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("event_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("device_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["user_devices.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_user_activity_logs_user_id_created_at", "user_activity_logs", ["user_id", "created_at"], unique=False)
    op.create_index("ix_user_activity_logs_event_type", "user_activity_logs", ["event_type"], unique=False)

    op.create_table(
        "user_biometric_data",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("biometric_type", sa.String(length=30), nullable=False),
        sa.Column("template_hash", sa.String(length=64), nullable=False),
        sa.Column("liveness_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("vendor", sa.String(length=50), nullable=True),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_user_biometric_data_user_id", "user_biometric_data", ["user_id"], unique=False)

    op.create_table(
        "user_preferences",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "key"),
    )
    op.create_index("ix_user_preferences_user_id", "user_preferences", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_table("user_preferences")
    op.drop_table("user_biometric_data")
    op.drop_table("user_activity_logs")
    op.drop_table("user_consent_records")
    op.drop_table("user_bank_accounts")
    op.drop_table("user_payment_methods")
    op.drop_table("user_addresses")
