"""Add third_party_integrations table, seeded with the 10 named integrations

Revision ID: 068
Revises: 067
Create Date: 2026-07-04 00:00:00.000000

Module 13 (System Settings) — a status/config view over the platform's
external integrations. Secrets are not stored here (they live wherever the
actual integration client reads them from — env vars / KMS, matching
mfa_secret_encrypted's pattern elsewhere); this table is deliberately just
operational metadata: is it configured, is it healthy, when was it last used.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import table, column

revision: str = '068'
down_revision: Union[str, None] = '067'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

integrations_table = table(
    "third_party_integrations",
    column("name", sa.String),
    column("category", sa.String),
    column("status", sa.String),
    column("config", postgresql.JSONB),
)

_SEED_INTEGRATIONS = [
    {"name": "Rye", "category": "checkout_automation", "status": "not_configured", "config": {}},
    {"name": "Lithic", "category": "virtual_cards", "status": "not_configured", "config": {}},
    {"name": "Jumio", "category": "kyc_verification", "status": "not_configured", "config": {}},
    {"name": "Safepay", "category": "payment_gateway", "status": "not_configured", "config": {}},
    {"name": "JazzCash", "category": "payment_gateway", "status": "not_configured", "config": {}},
    {"name": "EasyPaisa", "category": "payment_gateway", "status": "not_configured", "config": {}},
    {"name": "TCS", "category": "logistics", "status": "not_configured", "config": {}},
    {"name": "SendGrid", "category": "email", "status": "not_configured", "config": {}},
    {"name": "FCM", "category": "push_notifications", "status": "not_configured", "config": {}},
    {"name": "NADRA", "category": "identity_verification", "status": "not_configured", "config": {}},
]


def upgrade() -> None:
    op.create_table(
        "third_party_integrations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="not_configured"),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('not_configured','configured','healthy','degraded','failed')"),
        sa.ForeignKeyConstraint(["updated_by"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.bulk_insert(integrations_table, _SEED_INTEGRATIONS)

    for role in ("sk_app", "sk_admin"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON third_party_integrations TO {role}")
        op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}")


def downgrade() -> None:
    op.drop_table("third_party_integrations")
