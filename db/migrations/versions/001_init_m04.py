"""Init credit engine M04

Revision ID: 001_init_m04
Revises: 
Create Date: 2026-04-07 19:37:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_init_m04'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('credit_applications',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('application_type', sa.String(length=30), nullable=False),
        sa.Column('requested_limit', sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column('user_data_snapshot', sa.JSON(), nullable=True),
        sa.Column('credit_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('bureau_score', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='pending', nullable=False),
        sa.Column('approved_limit', sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column('rejection_code', sa.String(length=50), nullable=True),
        sa.Column('rejection_reason', sa.String(length=255), nullable=True),
        sa.Column('decided_by', sa.String(length=20), nullable=True),
        sa.Column('uuid', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid')
    )

    op.create_table('risk_assessments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('order_id', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('credit_app_id', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('assessment_type', sa.String(length=30), nullable=False),
        sa.Column('total_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('identity_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('device_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('behavioral_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('bank_statement_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('bureau_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('velocity_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('risk_band', sa.String(length=10), nullable=True),
        sa.Column('recommended_limit', sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column('down_payment_pct', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('flags', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('explanation', sa.JSON(), nullable=True),
        sa.Column('model_version', sa.String(length=20), nullable=True),
        sa.Column('processing_time_ms', sa.Integer(), nullable=True),
        sa.Column('uuid', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid')
    )

    op.create_table('credit_limit_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('old_limit', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('new_limit', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('reason_code', sa.String(length=50), nullable=False),
        sa.Column('changed_by_type', sa.String(length=50), nullable=False),
        sa.Column('changed_by_id', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('blacklisted_entities',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('entity_type', sa.String(length=30), nullable=False),
        sa.Column('entity_value', sa.String(length=255), nullable=False),
        sa.Column('reason_code', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('blacklisted_by', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('fraud_rules',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('rule_code', sa.String(length=50), nullable=False),
        sa.Column('rule_name', sa.String(length=255), nullable=False),
        sa.Column('condition_json', sa.JSON(), nullable=False),
        sa.Column('threshold', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('action', sa.String(length=20), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rule_code')
    )

    op.create_table('velocity_checks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('device_id', sa.String(length=255), nullable=True),
        sa.Column('ip_address', sa.String(length=50), nullable=True),
        sa.Column('check_type', sa.String(length=50), nullable=False),
        sa.Column('window_start', sa.DateTime(), nullable=False),
        sa.Column('window_end', sa.DateTime(), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False),
        sa.Column('threshold', sa.Integer(), nullable=False),
        sa.Column('breached', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade():
    op.drop_table('velocity_checks')
    op.drop_table('fraud_rules')
    op.drop_table('blacklisted_entities')
    op.drop_table('credit_limit_history')
    op.drop_table('risk_assessments')
    op.drop_table('credit_applications')
