"""Add vcn_kms_key_versions for production KMS envelope encryption of VCN PAN/CVV

Revision ID: 082
Revises: 081
Create Date: 2026-08-21 00:00:00.000000

VcnKeyProvider (apps/payment-orchestrator/src/services/vcn_encryption.py)
previously only supported a locally-derived Fernet key per version
(VCN_ENCRYPTION_KEY / VCN_ENCRYPTION_KEY_V2 / ...). The documented
production path — route new encryptions through AWS KMS envelope encryption
when ENVIRONMENT=production and KMS_KEY_ARN is set — raised
NotImplementedError, meaning VCN issuance had no working production
encryption story at all.

This table persists the KMS-encrypted data key (CiphertextBlob) generated
once per version via kms:GenerateDataKey, so any process/pod can rehydrate
the plaintext data key via kms:Decrypt without re-deriving it — the
plaintext data key itself is never persisted, only its KMS-wrapped form.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '082'
down_revision: Union[str, None] = '081'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vcn_kms_key_versions",
        sa.Column("version", sa.String(length=20), primary_key=True),
        sa.Column("kms_key_arn", sa.String(length=255), nullable=False),
        sa.Column("encrypted_data_key", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("vcn_kms_key_versions")
