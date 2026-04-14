"""Init M11 ledger

Revision ID: 011_init_m11_ledger
Revises: 010_init_m10_delivery
Create Date: 2026-04-12 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "011_init_m11_ledger"
down_revision: Union[str, None] = "010_init_m10_delivery"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ledger_accounts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_code", sa.String(length=20), nullable=False),
        sa.Column("account_name", sa.String(length=100), nullable=False),
        sa.Column("account_type", sa.String(length=20), nullable=False),
        sa.Column("normal_balance", sa.String(length=6), nullable=False),
        sa.Column("parent_account_id", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["parent_account_id"], ["ledger_accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_code"),
    )
    op.create_index("ix_ledger_accounts_account_code", "ledger_accounts", ["account_code"], unique=True)

    op.create_table(
        "charity_organizations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("bank_iban", sa.String(length=34), nullable=False),
        sa.Column("registration_number", sa.String(length=100), nullable=False),
        sa.Column("approved_by_shariah_board", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("approval_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("registration_number"),
        sa.UniqueConstraint("bank_iban"),
    )

    op.create_table(
        "journal_entries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_number", sa.String(length=30), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("entry_type", sa.String(length=30), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=True),
        sa.Column("source_id", sa.BigInteger(), nullable=True),
        sa.Column("is_balanced", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("total_debit", sa.Numeric(14, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("total_credit", sa.Numeric(14, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("total_debit >= 0", name="ck_journal_entries_total_debit_nonnegative"),
        sa.CheckConstraint("total_credit >= 0", name="ck_journal_entries_total_credit_nonnegative"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
        sa.UniqueConstraint("entry_number"),
        sa.UniqueConstraint("source_type", "source_id", name="uq_journal_entries_source"),
    )
    op.create_index("ix_journal_entries_entry_date", "journal_entries", ["entry_date"], unique=False)
    op.create_index("ix_journal_entries_source", "journal_entries", ["source_type", "source_id"], unique=False)

    op.create_table(
        "journal_entry_lines",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("journal_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("debit_amount", sa.Numeric(14, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("credit_amount", sa.Numeric(14, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("debit_amount >= 0", name="ck_journal_entry_lines_debit_nonnegative"),
        sa.CheckConstraint("credit_amount >= 0", name="ck_journal_entry_lines_credit_nonnegative"),
        sa.CheckConstraint("NOT (debit_amount > 0 AND credit_amount > 0)", name="ck_journal_entry_lines_one_side_only"),
        sa.ForeignKeyConstraint(["journal_id"], ["journal_entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["ledger_accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_journal_entry_lines_journal_id", "journal_entry_lines", ["journal_id"], unique=False)
    op.create_index("ix_journal_entry_lines_account_id", "journal_entry_lines", ["account_id"], unique=False)

    op.create_table(
        "late_fee_charity_allocations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("installment_id", sa.BigInteger(), nullable=False),
        sa.Column("loan_id", sa.BigInteger(), nullable=False),
        sa.Column("late_fee_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("charity_org_id", sa.BigInteger(), nullable=False),
        sa.Column("allocated_at", sa.DateTime(), nullable=False),
        sa.Column("disbursed_at", sa.DateTime(), nullable=True),
        sa.Column("receipt_s3", sa.String(length=512), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("late_fee_amount >= 0", name="ck_late_fee_charity_allocations_amount_nonnegative"),
        sa.ForeignKeyConstraint(["installment_id"], ["installments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["loan_id"], ["loans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["charity_org_id"], ["charity_organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("installment_id", name="uq_late_fee_charity_allocations_installment_id"),
    )
    op.create_index("ix_late_fee_charity_allocations_installment_id", "late_fee_charity_allocations", ["installment_id"], unique=False)
    op.create_index("ix_late_fee_charity_allocations_charity_org_id", "late_fee_charity_allocations", ["charity_org_id"], unique=False)

    op.execute(
        """
        INSERT INTO ledger_accounts (account_code, account_name, account_type, normal_balance, is_active, notes)
        VALUES
          ('1001', 'Cash / Bank', 'asset', 'debit', true, 'Operating cash and bank balances'),
          ('1100', 'AR - Installments', 'asset', 'debit', true, 'Customer receivable for installments'),
          ('1200', 'VCNs Issued', 'asset', 'debit', true, 'Value loaded into issued virtual cards'),
          ('2001', 'AP - Merchants', 'liability', 'credit', true, 'Merchant settlement payable'),
          ('2100', 'Charity Payable', 'liability', 'credit', true, 'Late-fee amounts reserved for charity'),
          ('2200', 'Customer Deposits', 'liability', 'credit', true, 'Down payments held before settlement'),
          ('3001', 'Owner Equity', 'equity', 'credit', true, 'Equity capital'),
          ('3900', 'Retained Earnings', 'equity', 'credit', true, 'Accumulated earnings'),
          ('4001', 'Murabaha Profit', 'revenue', 'credit', true, 'Disclosed profit on Murabaha sales'),
          ('4002', 'Affiliate Commission', 'revenue', 'credit', true, 'Partner and referral revenue'),
          ('4003', 'Late Fee Collections', 'revenue', 'credit', true, 'Legacy reporting bucket, should remain zero in platform P&L'),
          ('5001', 'COGS - Merchant Payment', 'expense', 'debit', true, 'Merchant acquisition cost'),
          ('5002', 'Gateway Fees', 'expense', 'debit', true, 'PSP and wallet fees'),
          ('5003', 'VCN Issuance', 'expense', 'debit', true, 'Card issuance cost'),
          ('5004', 'Loan Loss Provision', 'expense', 'debit', true, 'Expected credit loss reserve')
        ON CONFLICT (account_code) DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO charity_organizations (name, bank_iban, registration_number, approved_by_shariah_board, approval_date, is_active, notes)
        VALUES
          ('Edhi Foundation', 'PK00EDHI0000000000000000000', 'CHARITY-EDHI-001', true, CURRENT_DATE, true, 'Primary late-fee charity recipient'),
          ('Al-Khidmat Foundation', 'PK00ALKH000000000000000000', 'CHARITY-ALKH-001', true, CURRENT_DATE, true, 'Approved secondary charity recipient')
        ON CONFLICT (registration_number) DO NOTHING
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_name = 'installments'
            ) THEN
                BEGIN
                    CREATE INDEX IF NOT EXISTS ix_installments_due_date_status
                    ON installments (due_date, status)
                    WHERE status = 'pending';
                EXCEPTION WHEN duplicate_table THEN
                    NULL;
                END;
            END IF;
        END;
        $$;
        """
    )


def downgrade() -> None:
    op.drop_index("ix_late_fee_charity_allocations_charity_org_id", table_name="late_fee_charity_allocations")
    op.drop_index("ix_late_fee_charity_allocations_installment_id", table_name="late_fee_charity_allocations")
    op.drop_table("late_fee_charity_allocations")

    op.drop_index("ix_journal_entry_lines_account_id", table_name="journal_entry_lines")
    op.drop_index("ix_journal_entry_lines_journal_id", table_name="journal_entry_lines")
    op.drop_table("journal_entry_lines")

    op.drop_index("ix_journal_entries_source", table_name="journal_entries")
    op.drop_index("ix_journal_entries_entry_date", table_name="journal_entries")
    op.drop_table("journal_entries")

    op.drop_table("charity_organizations")
    op.drop_index("ix_ledger_accounts_account_code", table_name="ledger_accounts")
    op.drop_table("ledger_accounts")