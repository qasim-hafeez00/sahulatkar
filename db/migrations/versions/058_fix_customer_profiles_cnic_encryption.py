"""Store customer_profiles.cnic as encrypted bytes, matching KycService

Revision ID: 058
Revises: 057
Create Date: 2026-07-03 00:00:06.000000

KycService.upsert_profile has always encrypted the CNIC via KMSProvider before
storing it (consistent with wakalah_agreements.principal_cnic), but the column
was left as `varchar(15)` sized for plaintext — every profile write failed.
The unique constraint is dropped because KMS encryption isn't deterministic
(the same CNIC encrypts to different ciphertext each call), so it can no
longer enforce "one profile per real CNIC" at the DB level; a separate
deterministic CNIC-hash column would be needed to restore that guarantee.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '058'
down_revision: Union[str, None] = '057'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("customer_profiles_cnic_key", "customer_profiles", type_="unique")
    op.alter_column(
        "customer_profiles", "cnic",
        type_=sa.LargeBinary(),
        postgresql_using="NULL",
    )


def downgrade() -> None:
    op.alter_column(
        "customer_profiles", "cnic",
        type_=sa.String(15),
        postgresql_using="NULL",
    )
    op.create_unique_constraint("customer_profiles_cnic_key", "customer_profiles", ["cnic"])
