"""Enforce debit/credit exclusivity (XOR) on journal_entry_lines

Revision ID: 072
Revises: 071
Create Date: 2026-07-08 00:00:00.000000

Migration 011 added `ck_journal_entry_lines_one_side_only`
(`NOT (debit_amount > 0 AND credit_amount > 0)`), which only forbids a line
from having *both* a debit and a credit amount set. It does not forbid the
"neither" case -- a line with debit_amount = 0 AND credit_amount = 0 -- even
though such a line is meaningless in double-entry bookkeeping and is already
rejected at the application layer by
`src.domain.posting_engine.PostingLine.__post_init__`
("Line must have either a debit or credit amount").

This adds a DB-level `NOT (debit_amount = 0 AND credit_amount = 0)` check as
defense-in-depth, so the two constraints together enforce a true XOR: every
journal entry line must have exactly one of debit_amount/credit_amount
positive, never both and never neither. This matches
`047_ledger_hardening_remaining`'s and `070_fix_ledger_schema_orm_drift`'s
pattern of adding DB-level constraints on top of existing app-level
validation.
"""
from typing import Sequence, Union

from alembic import op


revision: str = '072'
down_revision: Union[str, None] = '071'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_journal_entry_lines_not_both_zero",
        "journal_entry_lines",
        "NOT (debit_amount = 0 AND credit_amount = 0)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_journal_entry_lines_not_both_zero", "journal_entry_lines", type_="check"
    )
