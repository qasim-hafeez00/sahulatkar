"""Enforce journal_entry_lines sum against journal_entries header via DB trigger

Revision ID: 085
Revises: 084
Create Date: 2026-08-28 00:00:00.000000

`chk_journal_entries_balanced` (migration 011 / sk_shared.models.ledger.JournalEntry)
only checks that journal_entries.total_debit == journal_entries.total_credit --
i.e. that the *header row itself* is internally consistent. It does NOT check
that the header's stated totals actually match what journal_entry_lines sums
to for that entry. Today this is safe only because
AccountingService._create_balanced_entry() is the sole writer of both tables
and always computes total_debit/total_credit from the same lines it inserts
(src/domain/posting_engine.assert_balanced() + accounting_service.py) -- there
is no DB-level guarantee against a future bypass (a bulk-load script, a raw
SQL fix-up, a bug in a future code path that touches journal_entry_lines
directly).

This adds a real DB-level guarantee: an AFTER INSERT OR UPDATE constraint
trigger on journal_entry_lines that recomputes SUM(debit_amount)/
SUM(credit_amount) grouped by journal_id and compares against the owning
journal_entries row's total_debit/total_credit, raising (and rolling back the
transaction) on any mismatch.

The trigger is declared DEFERRABLE INITIALLY DEFERRED because
AccountingService inserts a journal entry's lines one row at a time within a
single transaction (see `_create_balanced_entry`) -- an immediate (per-row)
trigger would spuriously reject the transaction after the first line of any
multi-line entry, before the remaining lines (already staged in the same
transaction) are inserted. Deferring to commit time lets all of an entry's
lines land first, matching how Postgres's own DEFERRABLE UNIQUE/FK
constraints are used elsewhere for the same reason, and how migration
047/070/072 layer DB-level checks on top of app-level validation in this
service.
"""
from typing import Sequence, Union

from alembic import op


revision: str = '085'
down_revision: Union[str, None] = '084'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_FUNCTION_NAME = "fn_check_journal_entry_lines_balanced"
_TRIGGER_NAME = "trg_journal_entry_lines_balance_check"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_FUNCTION_NAME}()
        RETURNS TRIGGER AS $$
        DECLARE
            v_journal_id BIGINT;
            v_line_debit NUMERIC(14, 2);
            v_line_credit NUMERIC(14, 2);
            v_header_debit NUMERIC(14, 2);
            v_header_credit NUMERIC(14, 2);
        BEGIN
            IF TG_OP = 'DELETE' THEN
                v_journal_id := OLD.journal_id;
            ELSE
                v_journal_id := NEW.journal_id;
            END IF;

            SELECT COALESCE(SUM(debit_amount), 0), COALESCE(SUM(credit_amount), 0)
              INTO v_line_debit, v_line_credit
              FROM journal_entry_lines
             WHERE journal_id = v_journal_id;

            SELECT total_debit, total_credit
              INTO v_header_debit, v_header_credit
              FROM journal_entries
             WHERE id = v_journal_id;

            IF v_header_debit IS NULL THEN
                RAISE EXCEPTION
                    'JOURNAL_ENTRY_LINES_ORPHANED: journal_entry_lines reference journal_id % with no matching journal_entries row',
                    v_journal_id;
            END IF;

            IF v_line_debit <> v_header_debit OR v_line_credit <> v_header_credit THEN
                RAISE EXCEPTION
                    'JOURNAL_ENTRY_LINES_SUM_MISMATCH: journal_id % lines sum to debit=%, credit=% but header states debit=%, credit=%',
                    v_journal_id, v_line_debit, v_line_credit, v_header_debit, v_header_credit;
            END IF;

            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER_NAME} ON journal_entry_lines;")
    op.execute(
        f"""
        CREATE CONSTRAINT TRIGGER {_TRIGGER_NAME}
        AFTER INSERT OR UPDATE ON journal_entry_lines
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION {_FUNCTION_NAME}();
        """
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER_NAME} ON journal_entry_lines;")
    op.execute(f"DROP FUNCTION IF EXISTS {_FUNCTION_NAME}();")
