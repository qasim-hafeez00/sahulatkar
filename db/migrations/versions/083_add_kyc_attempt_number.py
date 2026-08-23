"""Add attempt_number to user_kyc_verifications

Revision ID: 083
Revises: 082
Create Date: 2026-08-22 00:00:00.000000

Same class of drift as 059_add_kyc_verification_missing_columns.py: the
UserKycVerification model (packages/shared-python/sk_shared/models/kyc.py)
has had `attempt_number` since inception, and every KYC endpoint's SELECT
includes it, but no migration ever added the physical column — 059 caught
rejection_code/nadra_verified_at but missed this one. Broke every KYC read
(start/upload/submit/resubmit) with UndefinedColumnError.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '083'
down_revision: Union[str, None] = '082'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_kyc_verifications",
        sa.Column("attempt_number", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
    )


def downgrade() -> None:
    op.drop_column("user_kyc_verifications", "attempt_number")
