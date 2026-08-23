"""Add users.referred_by

Revision ID: 079
Revises: 078
Create Date: 2026-07-30 00:00:00.000003

Same class of bug as 078: `sk_shared.models.auth.User` declares
`referred_by: Mapped[Optional[int]]` (FK to users.id), but the live table only has an
unrelated `referred_by_user_id` column instead — nothing in apps/ or packages/ reads or
writes `referred_by_user_id` (grepped, zero hits), so it's left alone and this adds the
column the model actually needs.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '079'
down_revision: Union[str, None] = '078'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('referred_by', sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        'fk_users_referred_by', 'users', 'users', ['referred_by'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('fk_users_referred_by', 'users', type_='foreignkey')
    op.drop_column('users', 'referred_by')
