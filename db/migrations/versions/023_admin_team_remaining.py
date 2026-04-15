"""Admin Team Remaining

Revision ID: 023_admin_team_remaining
Revises: 022_marketing_growth
Create Date: 2026-04-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '023_admin_team_remaining'
down_revision: Union[str, None] = '022_marketing_growth'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Update users
    op.add_column('users', sa.Column('email', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('email_verified_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('first_name', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('last_name', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('date_of_birth', sa.Date(), nullable=True))
    op.add_column('users', sa.Column('gender', sa.String(length=1), nullable=True))
    op.add_column('users', sa.Column('cnic_encrypted', postgresql.BYTEA(), nullable=True))
    op.add_column('users', sa.Column('cnic_hash', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('cnic_verified_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('kyc_status', sa.String(length=20), server_default='pending', nullable=True))
    op.add_column('users', sa.Column('risk_level', sa.String(length=10), server_default='medium', nullable=True))
    op.add_column('users', sa.Column('credit_limit', sa.Numeric(14, 2), server_default=sa.text('0'), nullable=True))
    op.add_column('users', sa.Column('available_credit', sa.Numeric(14, 2), server_default=sa.text('0'), nullable=True))
    op.add_column('users', sa.Column('total_outstanding', sa.Numeric(14, 2), server_default=sa.text('0'), nullable=True))
    op.add_column('users', sa.Column('last_credit_assessment', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('mobile_operator', sa.String(length=20), nullable=True))
    op.add_column('users', sa.Column('preferred_language', sa.String(length=5), server_default='en', nullable=True))
    op.add_column('users', sa.Column('city', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('province', sa.String(length=50), nullable=True))
    op.add_column('users', sa.Column('referral_code', sa.String(length=20), nullable=True))
    op.add_column('users', sa.Column('referred_by_user_id', sa.BigInteger(), nullable=True))
    op.add_column('users', sa.Column('marketing_opt_in', sa.Boolean(), server_default=sa.text('false'), nullable=True))
    op.add_column('users', sa.Column('sms_opt_in', sa.Boolean(), server_default=sa.text('true'), nullable=True))
    op.add_column('users', sa.Column('push_opt_in', sa.Boolean(), server_default=sa.text('true'), nullable=True))
    op.add_column('users', sa.Column('registration_source', sa.String(length=50), nullable=True))
    op.add_column('users', sa.Column('registration_ip', postgresql.INET(), nullable=True))
    op.add_column('users', sa.Column('last_login_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('last_login_ip', postgresql.INET(), nullable=True))

    op.create_foreign_key("fk_users_referred_by_user_id", "users", "users", ["referred_by_user_id"], ["id"], ondelete="SET NULL")
    
    # gender constraint needs to be added as check constraint
    op.create_check_constraint('check_users_gender', 'users', "gender IN ('M','F','O')")


    op.create_table(
        "admin_user_roles",
        sa.Column("admin_user_id", sa.BigInteger(), nullable=False),
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.Column("assigned_by", sa.BigInteger(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["admin_user_id"], ["admin_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_by"], ["admin_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("admin_user_id", "role_id"),
    )
    op.create_index("ix_admin_user_roles_admin_user_id", "admin_user_roles", ["admin_user_id"], unique=False)
    op.create_index("ix_admin_user_roles_role_id", "admin_user_roles", ["role_id"], unique=False)

    op.create_table(
        "admin_activity_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("admin_user_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=True),
        sa.Column("target_id", sa.BigInteger(), nullable=True),
        sa.Column("before_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("session_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["admin_user_id"], ["admin_users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admin_activity_logs_admin_created_at", "admin_activity_logs", ["admin_user_id", sa.text("created_at DESC")], unique=False)
    op.create_index("ix_admin_activity_logs_target", "admin_activity_logs", ["target_type", "target_id"], unique=False)

    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("admin_user_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("device_info", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["admin_user_id"], ["admin_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_admin_sessions_admin__user_id_expires_at", "admin_sessions", ["admin_user_id", "expires_at"], unique=False)

    op.create_table(
        "system_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_sensitive", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )

    op.create_table(
        "feature_flags",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("flag_key", sa.String(length=100), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("rollout_percentage", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("target_user_ids", postgresql.ARRAY(sa.BigInteger()), nullable=True),
        sa.Column("target_cities", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("rollout_percentage BETWEEN 0 AND 100"),
        sa.ForeignKeyConstraint(["updated_by"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("flag_key"),
    )


def downgrade() -> None:
    op.drop_table("feature_flags")
    op.drop_table("system_settings")
    op.drop_table("admin_sessions")
    op.drop_table("admin_activity_logs")
    op.drop_table("admin_user_roles")

    op.drop_constraint('check_users_gender', 'users', type_='check')
    op.drop_constraint("fk_users_referred_by_user_id", "users", type_="foreignkey")
    
    op.drop_column('users', 'last_login_ip')
    op.drop_column('users', 'last_login_at')
    op.drop_column('users', 'registration_ip')
    op.drop_column('users', 'registration_source')
    op.drop_column('users', 'push_opt_in')
    op.drop_column('users', 'sms_opt_in')
    op.drop_column('users', 'marketing_opt_in')
    op.drop_column('users', 'referred_by_user_id')
    op.drop_column('users', 'referral_code')
    op.drop_column('users', 'province')
    op.drop_column('users', 'city')
    op.drop_column('users', 'preferred_language')
    op.drop_column('users', 'mobile_operator')
    op.drop_column('users', 'last_credit_assessment')
    op.drop_column('users', 'total_outstanding')
    op.drop_column('users', 'available_credit')
    op.drop_column('users', 'credit_limit')
    op.drop_column('users', 'risk_level')
    op.drop_column('users', 'kyc_status')
    op.drop_column('users', 'cnic_verified_at')
    op.drop_column('users', 'cnic_hash')
    op.drop_column('users', 'cnic_encrypted')
    op.drop_column('users', 'gender')
    op.drop_column('users', 'date_of_birth')
    op.drop_column('users', 'last_name')
    op.drop_column('users', 'first_name')
    op.drop_column('users', 'email_verified_at')
    op.drop_column('users', 'email')
