"""Reconcile wakalah_agreements/murabaha_contracts with the current contract models

Revision ID: 054
Revises: 053
Create Date: 2026-07-03 00:00:02.000000

Same class of drift as 052/053: the physical tables predate the current
sk_shared.models.contracts models.
  - wakalah_agreements: missing `principal_name_encrypted` (AES-256 encrypted
    name via KMSProvider, added by SEC-10); `principal_cnic` is varchar(20) in
    the DB but the model stores KMS-encrypted bytes there.
  - murabaha_contracts: the model's `total_sale_price` and `wakalah_agreement_id`
    columns are named `total_repayable` and `wakalah_id` in the DB. Neither name
    is referenced anywhere outside this table (verified: `wakalah_id` appears in
    no application code; `total_repayable` hits elsewhere are all Loan.total_repayable,
    an unrelated column on a different table), so renaming is safe. Both contract
    tables are empty in every environment this has been deployed to, since contract
    generation has never successfully completed until this fix.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '054'
down_revision: Union[str, None] = '053'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("wakalah_agreements", sa.Column("principal_name_encrypted", sa.LargeBinary(), nullable=True))
    op.alter_column(
        "wakalah_agreements", "principal_cnic",
        type_=sa.LargeBinary(),
        postgresql_using="NULL",
    )

    op.alter_column("murabaha_contracts", "total_repayable", new_column_name="total_sale_price")
    op.alter_column("murabaha_contracts", "wakalah_id", new_column_name="wakalah_agreement_id")


def downgrade() -> None:
    op.alter_column("murabaha_contracts", "wakalah_agreement_id", new_column_name="wakalah_id")
    op.alter_column("murabaha_contracts", "total_sale_price", new_column_name="total_repayable")

    op.alter_column(
        "wakalah_agreements", "principal_cnic",
        type_=sa.String(20),
        postgresql_using="NULL",
    )
    op.drop_column("wakalah_agreements", "principal_name_encrypted")
