"""Credit Engine Phase 0: align CreditLimitHistory with gateway usage, add policy versioning
and feature-snapshot tables

Revision ID: 074
Revises: 073
Create Date: 2026-07-23 00:00:00.000000

Three independent fixes, bundled because they're all part of the same credit-engine
redesign pass:

1. `credit_limit_history` gained a second, overlapping field-naming convention in gateway
   code (`apps/gateway/src/api/v1/orders.py`, `src/services/cart_service.py`,
   `src/api/v1/internal.py`'s credit-result callback) — `previous_limit`, `available_before`,
   `available_after`, `reason`, `changed_by` — none of which exist on the table. Gateway's
   writers guard every field with `hasattr(...)` so they degrade silently, but
   `orders.py::credit_history` reads `r.previous_limit` / `r.available_before` /
   `r.available_after` / `r.changed_by` with no guard at all — that endpoint raises
   `AttributeError` the first time it's hit against a populated table. Adding the missing
   columns (nullable, additive) makes both naming conventions work against the same table.
2. `credit_policy_versions`: versioned rule/scorecard config (prohibited categories, category
   risk multipliers, scorecard weights, thresholds) so the decision engine stops hardcoding
   these in Python (previously duplicated in `layer1_hard_blocks.py` and
   `layer6_order_overlay.py`).
3. `credit_feature_snapshots`: the frozen feature vector + additive score breakdown for each
   assessment — powers `/credit/explanation` and becomes the training set once loan outcomes
   mature.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '074'
down_revision: Union[str, None] = '073'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('credit_limit_history', sa.Column('previous_limit', sa.Numeric(14, 2), nullable=True))
    op.add_column('credit_limit_history', sa.Column('available_before', sa.Numeric(14, 2), nullable=True))
    op.add_column('credit_limit_history', sa.Column('available_after', sa.Numeric(14, 2), nullable=True))
    op.add_column('credit_limit_history', sa.Column('reason', sa.String(length=255), nullable=True))
    op.add_column('credit_limit_history', sa.Column('changed_by', sa.String(length=255), nullable=True))

    op.create_table(
        'credit_policy_versions',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('uuid', sa.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('version_label', sa.String(length=30), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='draft'),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(length=255), nullable=False),
        sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("status IN ('draft','active','retired')"),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid'),
        sa.UniqueConstraint('version_label'),
    )
    op.create_index(
        'ix_credit_policy_versions_active',
        'credit_policy_versions',
        ['status'],
        unique=False,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        'credit_feature_snapshots',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('uuid', sa.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('assessment_id', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('features', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('score_breakdown', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('policy_version', sa.String(length=30), nullable=True),
        sa.Column('model_version', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid'),
    )
    op.create_index('ix_credit_feature_snapshots_user_id', 'credit_feature_snapshots', ['user_id'], unique=False)
    op.create_index('ix_credit_feature_snapshots_assessment_id', 'credit_feature_snapshots', ['assessment_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_credit_feature_snapshots_assessment_id', table_name='credit_feature_snapshots')
    op.drop_index('ix_credit_feature_snapshots_user_id', table_name='credit_feature_snapshots')
    op.drop_table('credit_feature_snapshots')

    op.drop_index('ix_credit_policy_versions_active', table_name='credit_policy_versions')
    op.drop_table('credit_policy_versions')

    op.drop_column('credit_limit_history', 'changed_by')
    op.drop_column('credit_limit_history', 'reason')
    op.drop_column('credit_limit_history', 'available_after')
    op.drop_column('credit_limit_history', 'available_before')
    op.drop_column('credit_limit_history', 'previous_limit')
