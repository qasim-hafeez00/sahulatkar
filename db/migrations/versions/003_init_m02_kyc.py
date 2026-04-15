"""Init M02 KYC

Revision ID: 003_init_m02_kyc
Revises: 002_init_m01_auth
Create Date: 2026-04-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '003_init_m02_kyc'
down_revision: Union[str, None] = '002_init_m01_auth'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Customer Profiles
    op.create_table('customer_profiles',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('uuid', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('first_name', sa.String(length=100), nullable=False),
        sa.Column('last_name', sa.String(length=100), nullable=False),
        sa.Column('cnic', sa.String(length=15), nullable=False),
        sa.Column('dob', sa.DateTime(), nullable=False),
        sa.Column('address', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cnic'),
        sa.UniqueConstraint('user_id'),
        sa.UniqueConstraint('uuid')
    )

    # create enum type for status
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'kycstatus') THEN
                CREATE TYPE kycstatus AS ENUM ('pending', 'submitted', 'in_review', 'approved', 'rejected');
            END IF;
        END$$;
    """)

    # 2. User Kyc Verifications
    op.create_table('user_kyc_verifications',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('uuid', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'submitted', 'in_review', 'approved', 'rejected', name='kycstatus', create_type=False), nullable=False),
        sa.Column('cnic_front_image_url', sa.String(length=255), nullable=True),
        sa.Column('cnic_back_image_url', sa.String(length=255), nullable=True),
        sa.Column('liveness_video_url', sa.String(length=255), nullable=True),
        sa.Column('nadra_verification_data', sa.JSON(), nullable=True),
        sa.Column('shufti_verification_data', sa.JSON(), nullable=True),
        sa.Column('rejection_reason', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid')
    )
    op.create_index('ix_user_kyc_verifications_status', 'user_kyc_verifications', ['status'], unique=False)
    op.create_index('ix_user_kyc_verifications_user_id', 'user_kyc_verifications', ['user_id'], unique=False)

    # 3. Kyc Verification Queue
    op.create_table('kyc_verification_queue',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('kyc_verification_id', sa.BigInteger(), nullable=False),
        sa.Column('assigned_admin_id', sa.BigInteger(), nullable=True),
        sa.Column('claimed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['assigned_admin_id'], ['admin_users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['kyc_verification_id'], ['user_kyc_verifications.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('kyc_verification_id')
    )
    op.create_index('ix_kyc_verification_queue_assigned', 'kyc_verification_queue', ['assigned_admin_id'], unique=False)

def downgrade() -> None:
    op.drop_index('ix_kyc_verification_queue_assigned', table_name='kyc_verification_queue')
    op.drop_table('kyc_verification_queue')
    op.drop_index('ix_user_kyc_verifications_user_id', table_name='user_kyc_verifications')
    op.drop_index('ix_user_kyc_verifications_status', table_name='user_kyc_verifications')
    op.drop_table('user_kyc_verifications')
    
    # drop enum correctly
    op.execute("DROP TYPE IF EXISTS kycstatus")

    op.drop_table('customer_profiles')
