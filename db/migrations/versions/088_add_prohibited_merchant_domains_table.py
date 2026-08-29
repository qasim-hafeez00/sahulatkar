"""Add missing prohibited_merchant_domains table

Revision ID: 088
Revises: 087
Create Date: 2026-08-28 00:00:00.000000

`ProhibitedCheckerService.check_url` (apps/product-service/src/services/
prohibited_checker.py) has always issued a raw SQL query --
`SELECT domain FROM prohibited_merchant_domains WHERE lower(domain) = :domain
LIMIT 1` -- against a table that no migration in this repo's history ever
created. Found live-running the real end-to-end order flow against real
Postgres: SQLite (this repo's unit-test backend) tolerates the failing
statement because the surrounding `except Exception: pass` swallows it and
SQLite has no equivalent to Postgres's "current transaction is aborted"
semantics, so every unit test using this code path passes regardless. Real
Postgres does not forgive a failed statement inside an open transaction --
the very next statement on that same connection (the ProhibitedCategory
keyword check right after this one) fails too, with
`InFailedSQLTransactionError: current transaction is aborted`, which
`extract_or_enqueue` does NOT catch, surfacing as a 500 on every single
`POST /products/extract` call against real Postgres, i.e. in every real
non-test environment this code has ever run in. This is the actual root
cause the corresponding app-level fix (rolling back after the caught
exception, see prohibited_checker.py) closes structurally regardless of
whether this table exists -- this migration additionally makes the intended
merchant-domain-blocklist feature actually work instead of silently no-op'ing
forever, matching the schema style of the sibling `prohibited_categories`
table (migration 007).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '088'
down_revision: Union[str, None] = '087'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prohibited_merchant_domains",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("added_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("domain"),
    )
    op.create_index(
        "ix_prohibited_merchant_domains_domain",
        "prohibited_merchant_domains",
        ["domain"],
    )


def downgrade() -> None:
    op.drop_index("ix_prohibited_merchant_domains_domain", table_name="prohibited_merchant_domains")
    op.drop_table("prohibited_merchant_domains")
