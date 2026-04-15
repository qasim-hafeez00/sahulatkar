"""Shariah Remaining

Revision ID: 019_shariah_remaining
Revises: 018_delivery_remaining
Create Date: 2026-04-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '019_shariah_remaining'
down_revision: Union[str, None] = '018_delivery_remaining'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Update prohibited_categories
    op.add_column('prohibited_categories', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text("true")))

    op.create_table(
        "shariah_audit_reports",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("report_period", sa.String(length=20), nullable=False),
        sa.Column("audit_type", sa.String(length=20), nullable=False),
        sa.Column("findings", sa.Text(), nullable=True),
        sa.Column("recommendations", sa.Text(), nullable=True),
        sa.Column("board_member_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("report_pdf_s3", sa.String(length=512), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("audit_type IN ('quarterly','annual')"),
        sa.ForeignKeyConstraint(["created_by"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_shariah_audit_reports_period_type", "shariah_audit_reports", ["report_period", "audit_type"], unique=False)

    op.create_table(
        "shariah_board_approvals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("approval_type", sa.String(length=50), nullable=False),
        sa.Column("subject_reference", sa.String(length=100), nullable=False),
        sa.Column("scholar_name", sa.String(length=200), nullable=False),
        sa.Column("scholar_qualification", sa.Text(), nullable=True),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("conditions", sa.Text(), nullable=True),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("valid_until", sa.DateTime(), nullable=True),
        sa.Column("certificate_s3", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("approval_type IN ('contract_template','product_category','fee_structure','charity_org')"),
        sa.CheckConstraint("decision IN ('approved','rejected','conditional')"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_shariah_board_approvals_type_issued_at", "shariah_board_approvals", ["approval_type", sa.text("issued_at DESC")], unique=False)


def downgrade() -> None:
    op.drop_table("shariah_board_approvals")
    op.drop_table("shariah_audit_reports")

    op.drop_column('prohibited_categories', 'updated_at')
    op.drop_column('prohibited_categories', 'is_active')
