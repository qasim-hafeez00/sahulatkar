"""Make contract signed_at/valid_until columns timezone-aware

Revision ID: 055
Revises: 054
Create Date: 2026-07-03 00:00:03.000000

wakalah_agreements/murabaha_contracts.signed_at/valid_until and
contract_digital_signatures.signed_at were `TIMESTAMP WITHOUT TIME ZONE`, but
every write path builds these with datetime.now(timezone.utc) (tz-aware) —
asyncpg rejects binding a tz-aware value to a naive timestamp column outright,
so contract generation and signing has never been able to complete. Every
other timestamp column in this schema that's written the same way (Order,
Loan, VirtualCard, ...) is already `TIMESTAMP WITH TIME ZONE`; this brings the
three contract tables in line with that convention.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '055'
down_revision: Union[str, None] = '054'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("wakalah_agreements", "signed_at", type_=sa.DateTime(timezone=True))
    op.alter_column("wakalah_agreements", "valid_until", type_=sa.DateTime(timezone=True))
    op.alter_column("murabaha_contracts", "signed_at", type_=sa.DateTime(timezone=True))
    # murabaha_contracts never had a valid_until column at all, unlike wakalah_agreements —
    # the model's ContractGeneratorService.generate_murabaha sets it unconditionally.
    op.add_column("murabaha_contracts", sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("contract_digital_signatures", "signed_at", type_=sa.DateTime(timezone=True))


def downgrade() -> None:
    op.alter_column("contract_digital_signatures", "signed_at", type_=sa.DateTime(timezone=False))
    op.drop_column("murabaha_contracts", "valid_until")
    op.alter_column("murabaha_contracts", "signed_at", type_=sa.DateTime(timezone=False))
    op.alter_column("wakalah_agreements", "valid_until", type_=sa.DateTime(timezone=False))
    op.alter_column("wakalah_agreements", "signed_at", type_=sa.DateTime(timezone=False))
