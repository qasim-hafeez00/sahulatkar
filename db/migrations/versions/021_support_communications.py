"""Support Communications

Revision ID: 021_support_communications
Revises: 020_financial_accounting_remaining
Create Date: 2026-04-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '021_support_communications'
down_revision: Union[str, None] = '020_financial_accounting_remaining'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "support_tickets",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("ticket_number", sa.String(length=30), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=True),
        sa.Column("loan_id", sa.BigInteger(), nullable=True),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("priority", sa.String(length=10), nullable=False, server_default='medium'),
        sa.Column("status", sa.String(length=20), nullable=False, server_default='open'),
        sa.Column("assigned_to", sa.BigInteger(), nullable=True),
        sa.Column("sla_deadline", sa.DateTime(), nullable=True),
        sa.Column("first_response_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("satisfaction_score", sa.SmallInteger(), nullable=True),
        sa.Column("satisfaction_comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("category IN ('payment_issue','delivery_issue','product_issue','kyc_query','fraud_report','refund_request','contract_query','account_issue','general')"),
        sa.CheckConstraint("priority IN ('low','medium','high','urgent')"),
        sa.CheckConstraint("status IN ('open','in_progress','waiting_user','escalated','resolved','closed')"),
        sa.CheckConstraint("satisfaction_score BETWEEN 1 AND 5"),
        sa.ForeignKeyConstraint(["assigned_to"], ["admin_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["loan_id"], ["loans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_number"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_support_tickets_user_id", "support_tickets", ["user_id"], unique=False)
    op.create_index("ix_support_tickets_status", "support_tickets", ["status"], unique=False)
    op.create_index("ix_support_tickets_assigned_to_status", "support_tickets", ["assigned_to", "status"], unique=False)

    op.create_table(
        "ticket_messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("ticket_id", sa.BigInteger(), nullable=False),
        sa.Column("sender_type", sa.String(length=20), nullable=False),
        sa.Column("sender_id", sa.BigInteger(), nullable=True),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("attachments_s3", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("is_internal_note", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("sender_type IN ('user','agent','system','chatbot')"),
        sa.ForeignKeyConstraint(["ticket_id"], ["support_tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_ticket_messages_ticket_id_created_at", "ticket_messages", ["ticket_id", "created_at"], unique=False)

    op.create_table(
        "email_templates",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("template_code", sa.String(length=100), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False, server_default='en'),
        sa.Column("subject_template", sa.String(length=255), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("required_variables", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("version", sa.String(length=10), nullable=False, server_default='1.0'),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("language IN ('en','ur')"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_code"),
    )
    op.create_index("ix_email_templates_code_lang", "email_templates", ["template_code", "language"], unique=False)

    op.create_table(
        "sms_templates",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("template_code", sa.String(length=100), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False, server_default='en'),
        sa.Column("body_en", sa.Text(), nullable=False),
        sa.Column("body_ur", sa.Text(), nullable=True),
        sa.Column("max_length", sa.SmallInteger(), nullable=False, server_default=sa.text("160")),
        sa.Column("gateway_template_id", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("language IN ('en','ur')"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_code", "language"),
    )

    op.create_table(
        "notifications_queue",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("notification_type", sa.String(length=50), nullable=False),
        sa.Column("template_id", sa.BigInteger(), nullable=True),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("variables", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("recipient", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default='queued'),
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default=sa.text("5")),
        sa.Column("scheduled_at", sa.DateTime(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("gateway_message_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("channel IN ('sms','email','push','whatsapp')"),
        sa.CheckConstraint("status IN ('queued','sending','sent','failed','bounced','cancelled')"),
        sa.CheckConstraint("priority BETWEEN 1 AND 10"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_notifications_queue_user_id", "notifications_queue", ["user_id"], unique=False)

    op.create_table(
        "customer_communications",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("gateway_message_id", sa.String(length=255), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.Column("delivery_status", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("channel IN ('sms','email','push','whatsapp')"),
        sa.CheckConstraint("direction IN ('inbound','outbound')"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customer_communications_user_id_sent_at", "customer_communications", ["user_id", sa.text("sent_at DESC")], unique=False)

    op.create_table(
        "canned_responses",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("language", sa.String(length=2), nullable=False, server_default='en'),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("canned_responses")
    op.drop_table("customer_communications")
    op.drop_table("notifications_queue")
    op.drop_table("sms_templates")
    op.drop_table("email_templates")
    op.drop_table("ticket_messages")
    op.drop_table("support_tickets")
