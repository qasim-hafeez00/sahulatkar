"""Credit Risk Remaining

Revision ID: 014_credit_risk_remaining
Revises: 013_user_identity_remaining
Create Date: 2026-04-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '014_credit_risk_remaining'
down_revision: Union[str, None] = '013_user_identity_remaining'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "fraud_alerts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("order_id", sa.BigInteger(), nullable=True),
        sa.Column("payment_id", sa.BigInteger(), nullable=True),
        sa.Column("alert_type", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=True),
        sa.Column("rule_code", sa.String(length=50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default='open'),
        sa.Column("investigated_by", sa.BigInteger(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("action_taken", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("alert_type IN ('synthetic_identity','account_takeover','velocity_breach','device_anomaly','collusion_merchant','sim_swap_suspected','cross_border_risk','bot_detection','document_forgery','address_mismatch')"),
        sa.CheckConstraint("severity IN ('low','medium','high','critical')"),
        sa.CheckConstraint("source IN ('rule_engine','ml_model','manual','watchlist')"),
        sa.CheckConstraint("status IN ('open','investigating','resolved_genuine','resolved_fraud','false_positive')"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_fraud_alerts_user_id", "fraud_alerts", ["user_id"], unique=False)
    op.create_index("ix_fraud_alerts_status", "fraud_alerts", ["status"], unique=False)
    op.create_index("ix_fraud_alerts_severity_created_at", "fraud_alerts", ["severity", "created_at"], unique=False)

    op.create_table(
        "manual_review_queue",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("entity_type", sa.String(length=30), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=False),
        sa.Column("queue_type", sa.String(length=30), nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default=sa.text("3")),
        sa.Column("assigned_to", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default='pending'),
        sa.Column("sla_deadline", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("priority BETWEEN 1 AND 5"),
        sa.CheckConstraint("status IN ('pending','in_review','resolved','escalated')"),
        sa.ForeignKeyConstraint(["assigned_to"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_manual_review_queue_status_priority", "manual_review_queue", ["status", "priority"], unique=False)
    op.create_index("ix_manual_review_queue_assigned_to_status", "manual_review_queue", ["assigned_to", "status"], unique=False)

    op.create_table(
        "bank_statement_analysis",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("avg_balance", sa.Numeric(14, 2), nullable=True),
        sa.Column("income_estimate", sa.Numeric(14, 2), nullable=True),
        sa.Column("expense_ratio", sa.Numeric(5, 4), nullable=True),
        sa.Column("salary_detected", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("nsf_events", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("source", sa.String(length=30), nullable=True),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_bank_statement_analysis_user_id_period_start", "bank_statement_analysis", ["user_id", sa.text("period_start DESC")], unique=False)

    op.create_table(
        "device_fingerprints",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("raw_fingerprint", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("computed_hash", sa.String(length=64), nullable=False),
        sa.Column("risk_flags", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("is_known_fraud_device", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("computed_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_device_fingerprints_user_id", "device_fingerprints", ["user_id"], unique=False)
    op.create_index("ix_device_fingerprints_computed_hash", "device_fingerprints", ["computed_hash"], unique=False)
    op.create_index("ix_device_fingerprints_is_known_fraud_device", "device_fingerprints", ["is_known_fraud_device"], unique=False)

    op.create_table(
        "ip_intelligence",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ip", postgresql.INET(), nullable=False),
        sa.Column("country", sa.String(length=50), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("isp", sa.String(length=100), nullable=True),
        sa.Column("is_proxy", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_vpn", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_tor", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("threat_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("looked_up_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ip"),
    )

    op.create_table(
        "synthetic_identity_indicators",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("indicator_type", sa.String(length=50), nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("supporting_signals", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("model_version", sa.String(length=20), nullable=True),
        sa.Column("flagged_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_synthetic_identity_indicators_user_id_flagged_at", "synthetic_identity_indicators", ["user_id", sa.text("flagged_at DESC")], unique=False)

def downgrade() -> None:
    op.drop_table("synthetic_identity_indicators")
    op.drop_table("ip_intelligence")
    op.drop_table("device_fingerprints")
    op.drop_table("bank_statement_analysis")
    op.drop_table("manual_review_queue")
    op.drop_table("fraud_alerts")
