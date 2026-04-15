"""Init M05 Contracts

Revision ID: 004_init_m05_contracts
Revises: 003_init_m02_kyc
Create Date: 2026-04-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "004_init_m05_contracts"
down_revision: Union[str, None] = "003_init_m02_kyc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. wakalah_agreements (WITHOUT order_id FK for now to break circularity)
    op.create_table(
        "wakalah_agreements",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False), # Placeholder for value, FK added in 006
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("contract_number", sa.String(length=50), nullable=False),
        sa.Column("authorized_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("contract_pdf_path", sa.Text(), nullable=False),
        sa.Column("contract_hash", sa.String(length=64), nullable=False),
        sa.Column("otp_reference", sa.String(length=64), nullable=False),
        sa.Column("signed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column('principal_name', sa.String(length=200), nullable=True),
        sa.Column('principal_cnic', sa.String(length=20), nullable=True),
        sa.Column('principal_phone', sa.String(length=20), nullable=True),
        sa.Column('agent_name', sa.String(length=100), server_default='SahulatKar (Pvt) Ltd.', nullable=False),
        sa.Column('agent_secp_license', sa.String(length=50), server_default='SECP-L-12345', nullable=False),
        sa.Column('product_description', sa.Text(), nullable=True),
        sa.Column('merchant_name', sa.String(length=255), nullable=True),
        sa.Column('product_url', sa.String(length=2048), nullable=True),
        sa.Column('price_variance_pct', sa.Numeric(precision=4, scale=2), server_default='5.00', nullable=False),
        sa.Column('valid_until', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contract_number"),
        sa.UniqueConstraint("uuid"),
    )

    # 2. murabaha_contracts
    op.create_table(
        "murabaha_contracts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False), # FK added in 006
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("wakalah_agreement_id", sa.BigInteger(), nullable=True),
        sa.Column("contract_number", sa.String(length=50), nullable=False),
        sa.Column("cost_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("profit_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("profit_rate_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("total_sale_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("installment_count", sa.Integer(), nullable=False),
        sa.Column("installment_schedule", sa.JSON(), nullable=False),
        sa.Column("contract_pdf_path", sa.Text(), nullable=False),
        sa.Column("contract_hash", sa.String(length=64), nullable=False),
        sa.Column("otp_reference", sa.String(length=64), nullable=False),
        sa.Column("signed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column('currency', sa.String(length=3), server_default='PKR', nullable=False),
        sa.Column('template_version', sa.String(length=10), server_default='1.0', nullable=False),
        sa.Column('validated_by_shariah_board', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["wakalah_agreement_id"], ["wakalah_agreements.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contract_number"),
        sa.UniqueConstraint("uuid"),
    )

    # 3. contract_digital_signatures
    op.create_table(
        "contract_digital_signatures",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("wakalah_agreement_id", sa.BigInteger(), nullable=True),
        sa.Column("murabaha_contract_id", sa.BigInteger(), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("signature_type", sa.String(length=50), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("device_id", sa.String(length=255), nullable=True),
        sa.Column("otp_hash", sa.String(length=64), nullable=False),
        sa.Column("signed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["wakalah_agreement_id"], ["wakalah_agreements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["murabaha_contract_id"], ["murabaha_contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )


def downgrade() -> None:
    op.drop_table("contract_digital_signatures")
    op.drop_table("murabaha_contracts")
    op.drop_table("wakalah_agreements")
