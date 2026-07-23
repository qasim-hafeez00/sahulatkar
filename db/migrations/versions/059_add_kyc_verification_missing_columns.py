"""Add rejection_code/nadra_verified_at to user_kyc_verifications

Revision ID: 059
Revises: 058
Create Date: 2026-07-03 00:00:07.000000

Same class of drift as the orders/contracts/payments tables: the
UserKycVerification model has `rejection_code` and `nadra_verified_at`
(selected by every query the KYC router runs, including the simple
`GET/POST /kyc/start` read), but the physical table never had them.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '059'
down_revision: Union[str, None] = '058'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_kyc_verifications", sa.Column("rejection_code", sa.String(50), nullable=True))
    # timezone=True: KycService always writes datetime.now(timezone.utc) here.
    op.add_column("user_kyc_verifications", sa.Column("nadra_verified_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("user_kyc_verifications", "nadra_verified_at")
    op.drop_column("user_kyc_verifications", "rejection_code")
