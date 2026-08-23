"""Add users.risk_band and users.next_review_date

Revision ID: 078
Revises: 077
Create Date: 2026-07-30 00:00:00.000002

`sk_shared.models.auth.User` (the model gateway's AuthService actually queries)
declares `risk_band: Mapped[Optional[str]]` and `next_review_date: Mapped[Optional[datetime]]`,
but neither column exists on the live `users` table — every `/auth/register/initiate`
call 500s with `asyncpg.exceptions.UndefinedColumnError: column users.risk_band does not
exist` before it can even check whether the phone number is taken. The table does have an
unrelated `risk_level` column, but nothing in the codebase reads or writes it (grepped
apps/ and packages/ for `risk_level` — zero hits), so this adds the two columns the model
actually needs rather than renaming/touching the orphaned one.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '078'
down_revision: Union[str, None] = '077'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('risk_band', sa.String(length=10), nullable=True))
    op.add_column('users', sa.Column('next_review_date', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'next_review_date')
    op.drop_column('users', 'risk_band')
