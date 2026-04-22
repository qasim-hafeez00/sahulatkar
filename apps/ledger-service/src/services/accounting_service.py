from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable
from uuid import uuid4
import calendar
import re

from sqlalchemy import func, select
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sk_shared.models.ledger import CharityOrganization, JournalEntry, JournalEntryLine, LateFeeCharityAllocation, LedgerAccount
from sk_shared.models.payment import Installment, Loan
from sk_shared.redis_client import RedisClient

from src.accounting.accounts import ACCOUNT_CODES
from src.core.period_utils import get_period_bounds
from src.core.readonly_guard import readonly_guard
from src.domain.posting_engine import PostingLine, assert_balanced, validate_entry_metadata
from src.events.publisher import EventPublisher
from src.services.period_service import PeriodService
from src.services.balance_service import BalanceService


@dataclass(slots=True)
class JournalEntryResult:
    journal_entry: JournalEntry
    created: bool


class AccountingService:
    def __init__(self, db_session: AsyncSession, redis: RedisClient | None = None) -> None:
        self.db = db_session
        self.period_service = PeriodService(db_session)
        self.balance_service = BalanceService(db_session)
        self.publisher = EventPublisher(redis) if redis else None

    async def record_down_payment(self, order_id: int, amount: Decimal | float | int) -> JournalEntryResult:
        result = await self._create_balanced_entry(
            entry_type="payment_received",
            source_type="payment.down_payment_confirmed",
            source_id=order_id,
            description=f"Down payment received for order {order_id}",
            lines=[
                PostingLine(ACCOUNT_CODES["cash"], debit_amount=self._money(amount)),
                PostingLine(ACCOUNT_CODES["customer_deposits"], credit_amount=self._money(amount)),
            ],
        )
        if result.created:
            await self.db.commit()
            await self.db.refresh(result.journal_entry)
        return result

    async def record_purchase(self, order_id: int, cost_amount: Decimal | float | int, total_amount: Decimal | float | int, vcn_id: int) -> JournalEntryResult:
        """
        Record the Murabaha Sale transaction.
        Procurement was already handled (Dr VCN / Cr Cash).
        Now we record the Sale: (Dr) AR-Installments / (Cr) VCN-Asset / (Cr) Murabaha Profit.
        """
        cost = self._money(cost_amount)
        total = self._money(total_amount)
        profit = total - cost
        if profit < 0:
            raise ValueError("Purchase total cannot be less than cost")

        result = await self._create_balanced_entry(
            entry_type="vcn_charge",
            source_type="vcn_charge",
            source_id=vcn_id,
            description=f"Murabaha sale recorded for order {order_id} via VCN {vcn_id}",
            lines=[
                PostingLine(ACCOUNT_CODES["ar_installments"], debit_amount=total),
                PostingLine(ACCOUNT_CODES["vcn_issued"], credit_amount=cost),
                PostingLine(ACCOUNT_CODES["murabaha_profit"], credit_amount=profit),
            ],
        )
        
        if result.created:
            await self.db.commit()
            await self.db.refresh(result.journal_entry)
        return result

    @readonly_guard
    async def record_installment_paid(self, installment_id: int, amount: Decimal | float | int) -> JournalEntryResult:
        installment = await self._get_installment(installment_id)
        result = await self._create_balanced_entry(
            entry_type="payment_received",
            source_type="installment.paid",
            source_id=installment_id,
            description=f"Installment {installment.installment_number} paid for loan {installment.loan_id}",
            lines=[
                PostingLine(ACCOUNT_CODES["cash"], debit_amount=self._money(amount)),
                PostingLine(ACCOUNT_CODES["ar_installments"], credit_amount=self._money(amount)),
            ],
        )
        if result.created:
            await self.db.commit()
            await self.db.refresh(result.journal_entry)
        return result

    @readonly_guard
    async def record_late_fee(self, installment_id: int, amount: Decimal | float | int) -> JournalEntryResult:
        installment = await self._get_installment(installment_id)
        charity_org = await self._get_default_charity_org()
        result = await self._create_balanced_entry(
            entry_type="late_fee",
            source_type="installment.late_fee",
            source_id=installment_id,
            description=f"Late fee recorded for installment {installment.installment_number}",
            lines=[
                PostingLine(ACCOUNT_CODES["ar_installments"], debit_amount=self._money(amount)),
                PostingLine(ACCOUNT_CODES["charity_payable"], credit_amount=self._money(amount)),
            ],
        )
        allocation = LateFeeCharityAllocation(
            installment_id=installment.id,
            loan_id=installment.loan_id,
            late_fee_amount=self._money(amount),
            charity_org_id=charity_org.id,
            allocated_at=datetime.now(timezone.utc),
        )
        self.db.add(allocation)
        if result.created:
            await self.db.commit()
            await self.db.refresh(result.journal_entry)
        return result

    async def record_charity_disbursement(self, source_id: int, amount: Decimal | float | int, reference: str | None = None) -> JournalEntryResult:
        disbursement_amount = self._money(amount)
        result = await self._create_balanced_entry(
            entry_type="charity_disbursement",
            source_type="charity.disbursement",
            source_id=source_id,
            description=f"Charity disbursement recorded{f' ({reference})' if reference else ''}",
            lines=[
                PostingLine(ACCOUNT_CODES["charity_payable"], debit_amount=disbursement_amount),
                PostingLine(ACCOUNT_CODES["cash"], credit_amount=disbursement_amount),
            ],
        )
        if result.created:
            await self.db.commit()
            await self.db.refresh(result.journal_entry)
        return result

    async def record_vcn_load(self, vcn_id: int, amount: Decimal | float | int) -> JournalEntryResult:
        load_amount = self._money(amount)
        result = await self._create_balanced_entry(
            entry_type="vcn_load",
            source_type="vcn.load",
            source_id=vcn_id,
            description=f"VCN load recorded for VCN {vcn_id}",
            lines=[
                PostingLine(ACCOUNT_CODES["vcn_issued"], debit_amount=load_amount),
                PostingLine(ACCOUNT_CODES["cash"], credit_amount=load_amount),
            ],
        )
        if result.created:
            await self.db.commit()
            await self.db.refresh(result.journal_entry)
        return result

    async def record_merchant_payment(self, order_id: int, amount: Decimal | float | int) -> JournalEntryResult:
        payment_amount = self._money(amount)
        result = await self._create_balanced_entry(
            entry_type="merchant_payment",
            source_type="merchant.payment",
            source_id=order_id,
            description=f"Merchant payment recorded for order {order_id}",
            lines=[
                PostingLine(ACCOUNT_CODES["cogs_merchant_payment"], debit_amount=payment_amount),
                PostingLine(ACCOUNT_CODES["cash"], credit_amount=payment_amount),
            ],
        )
        if result.created:
            await self.db.commit()
            await self.db.refresh(result.journal_entry)
        return result

    async def record_gateway_fee(self, transaction_id: int, amount: Decimal | float | int) -> JournalEntryResult:
        fee_amount = self._money(amount)
        result = await self._create_balanced_entry(
            entry_type="gateway_fee",
            source_type="payment.gateway_fee",
            source_id=transaction_id,
            description=f"Gateway fee recorded for transaction {transaction_id}",
            lines=[
                PostingLine(ACCOUNT_CODES["gateway_fees"], debit_amount=fee_amount),
                PostingLine(ACCOUNT_CODES["cash"], credit_amount=fee_amount),
            ],
        )
        if result.created:
            await self.db.commit()
            await self.db.refresh(result.journal_entry)
        return result

    async def record_refund(self, transaction_id: int, amount: Decimal | float | int) -> JournalEntryResult:
        refund_amount = self._money(amount)
        result = await self._create_balanced_entry(
            entry_type="refund",
            source_type="payment.refund",
            source_id=transaction_id,
            description=f"Refund recorded for transaction {transaction_id}",
            lines=[
                PostingLine(ACCOUNT_CODES["ar_installments"], debit_amount=refund_amount),
                PostingLine(ACCOUNT_CODES["cash"], credit_amount=refund_amount),
            ],
        )
        if result.created:
            await self.db.commit()
            await self.db.refresh(result.journal_entry)
        return result

    async def record_chargeback(self, transaction_id: int, amount: Decimal | float | int) -> JournalEntryResult:
        chargeback_amount = self._money(amount)
        result = await self._create_balanced_entry(
            entry_type="chargeback",
            source_type="payment.chargeback",
            source_id=transaction_id,
            description=f"Chargeback recorded for transaction {transaction_id}",
            lines=[
                PostingLine(ACCOUNT_CODES["ar_installments"], debit_amount=chargeback_amount),
                PostingLine(ACCOUNT_CODES["cash"], credit_amount=chargeback_amount),
            ],
        )
        if result.created:
            await self.db.commit()
            await self.db.refresh(result.journal_entry)
        return result

    async def record_provision(self, provision_id: int, amount: Decimal | float | int) -> JournalEntryResult:
        provision_amount = self._money(amount)
        result = await self._create_balanced_entry(
            entry_type="provision",
            source_type="loan.provision",
            source_id=provision_id,
            description=f"Loan loss provision recorded for reference {provision_id}",
            lines=[
                PostingLine(ACCOUNT_CODES["loan_loss_provision"], debit_amount=provision_amount),
                PostingLine(ACCOUNT_CODES["loan_loss_reserve"], credit_amount=provision_amount),
            ],
        )
        if result.created:
            await self.db.commit()
            await self.db.refresh(result.journal_entry)
        return result

    async def record_write_off(self, write_off_id: int, amount: Decimal | float | int) -> JournalEntryResult:
        write_off_amount = self._money(amount)
        result = await self._create_balanced_entry(
            entry_type="write_off",
            source_type="loan.write_off",
            source_id=write_off_id,
            description=f"Loan write-off recorded for reference {write_off_id}",
            lines=[
                PostingLine(ACCOUNT_CODES["loan_loss_reserve"], debit_amount=write_off_amount),
                PostingLine(ACCOUNT_CODES["ar_installments"], credit_amount=write_off_amount),
            ],
        )
        if result.created:
            await self.db.commit()
            await self.db.refresh(result.journal_entry)
        return result

    async def record_manual_adjustment(
        self,
        adjustment_id: int | str,
        amount: Decimal | float | int,
        account_code: str,
        counter_account_code: str,
        debit_to_account: bool,
        description: str | None = None,
        entry_date: date | None = None,
    ) -> JournalEntryResult:
        adjustment_amount = self._money(amount)
        detail = description or f"Manual adjustment {adjustment_id}"
        if debit_to_account:
            lines = [
                PostingLine(account_code, debit_amount=adjustment_amount),
                PostingLine(counter_account_code, credit_amount=adjustment_amount),
            ]
        else:
            lines = [
                PostingLine(account_code, credit_amount=adjustment_amount),
                PostingLine(counter_account_code, debit_amount=adjustment_amount),
            ]

        result = await self._create_balanced_entry(
            entry_type="manual_adjustment",
            source_type="ledger.manual_adjustment",
            source_id=adjustment_id,
            description=detail,
            lines=lines,
            entry_date=entry_date,
        )
        if result.created:
            await self.db.commit()
            await self.db.refresh(result.journal_entry)
        return result

    async def record_manual_entry(
        self,
        *,
        lines: list[dict[str, object]],
        description: str,
        entry_date: date | None = None,
        reference: str | None = None,
    ) -> JournalEntryResult:
        """Create a manual journal entry from finance admin input."""
        posting_lines = [
            PostingLine(
                account_code=str(line["account_code"]),
                debit_amount=self._money(line.get("debit_amount", 0)),
                credit_amount=self._money(line.get("credit_amount", 0)),
                description=line.get("description"),
            )
            for line in lines
        ]
        
        # For manual entries, we use a random source_id to avoid collision, 
        # but reference can be provided for idempotency.
        source_id = reference or f"MAN-{uuid4().hex[:12].upper()}"
        
        result = await self._create_balanced_entry(
            entry_type="manual",
            source_type="ledger.manual_entry",
            source_id=source_id,
            description=description,
            lines=posting_lines,
            entry_date=entry_date,
        )
        if result.created:
            await self.db.commit()
            await self.db.refresh(result.journal_entry)
        return result

    async def record_reversal(
        self,
        reversal_id: int | str,
        original_entry_number: str | None = None,
        original_source_type: str | None = None,
        original_source_id: int | str | None = None,
        reason: str | None = None,
        entry_date: date | None = None,
    ) -> JournalEntryResult:
        """Reverse an existing journal entry by creating an opposite entry."""
        original_stmt = select(JournalEntry).options(
            selectinload(JournalEntry.lines).selectinload(JournalEntryLine.account)
        )
        if original_entry_number:
            original_stmt = original_stmt.where(JournalEntry.entry_number == original_entry_number)
        elif original_source_type and original_source_id:
            original_stmt = original_stmt.where(
                JournalEntry.source_type == original_source_type,
                JournalEntry.source_id == original_source_id,
            )
        else:
            raise ValueError("Provide either original_entry_number or original_source_type/id")

        original = (await self.db.execute(original_stmt)).scalar_one_or_none()
        if original is None:
            raise LookupError("ORIGINAL_ENTRY_NOT_FOUND")

        if original.entry_type == "reversal":
            raise ValueError("CANNOT_REVERSE_A_REVERSAL")

        # INC-03: Double-reversal guard
        if original.reversed_by_id is not None:
            raise ValueError("ENTRY_ALREADY_REVERSED")

        reversal_lines = []
        for line in original.lines:
            reversal_lines.append(
                PostingLine(
                    line.account.account_code,
                    debit_amount=self._money(line.credit_amount),
                    credit_amount=self._money(line.debit_amount),
                    description=f"Reversal of {original_entry_number}",
                )
            )

        result = await self._create_balanced_entry(
            entry_type="reversal",
            source_type="ledger.reversal",
            source_id=reversal_id,
            description=f"Reversal for {original_entry_number}{f' - {reason}' if reason else ''}",
            lines=reversal_lines,
            entry_date=entry_date or date.today(),
        )
        if result.created:
            # Mark the original entry as reversed
            original.reversed_by_id = result.journal_entry.id
            await self.db.commit()
            await self.db.refresh(result.journal_entry)
        return result

    async def build_profit_loss_report(self, period: str) -> dict[str, object]:
        # Generate all monthly period keys within the requested period range
        start_date, end_date = get_period_bounds(period)
        period_keys = []
        curr = start_date.replace(day=1)
        while curr <= end_date:
            period_keys.append(f"{curr.year}-{curr.month:02d}")
            # Move to next month
            if curr.month == 12:
                curr = date(curr.year + 1, 1, 1)
            else:
                curr = date(curr.year, curr.month + 1, 1)

        revenue_accounts = {ACCOUNT_CODES["murabaha_profit"], ACCOUNT_CODES["affiliate_commission"], ACCOUNT_CODES["late_fee_collections"]}
        expense_accounts = {ACCOUNT_CODES["cogs_merchant_payment"], ACCOUNT_CODES["gateway_fees"], ACCOUNT_CODES["vcn_issuance"], ACCOUNT_CODES["loan_loss_provision"]}

        revenue_stmt = (
            select(func.coalesce(func.sum(JournalEntryLine.credit_amount), 0), func.coalesce(func.sum(JournalEntryLine.debit_amount), 0))
            .join(LedgerAccount, LedgerAccount.id == JournalEntryLine.account_id)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_id)
            .where(LedgerAccount.account_code.in_(revenue_accounts))
            .where(JournalEntry.period_key.in_(period_keys))
        )
        expense_stmt = (
            select(func.coalesce(func.sum(JournalEntryLine.debit_amount), 0))
            .join(LedgerAccount, LedgerAccount.id == JournalEntryLine.account_id)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_id)
            .where(LedgerAccount.account_code.in_(expense_accounts))
            .where(JournalEntry.period_key.in_(period_keys))
        )
        revenue_credit, revenue_debit = (await self.db.execute(revenue_stmt)).one()
        expenses = (await self.db.execute(expense_stmt)).scalar_one()
        revenue = Decimal(str(revenue_credit)) - Decimal(str(revenue_debit))
        cost_of_sales = Decimal(str(expenses))
        net_income = revenue - cost_of_sales
        margin_pct = (net_income / revenue * Decimal("100")) if revenue else Decimal("0")
        return {
            "period": period,
            "revenue": float(revenue),
            "costs": float(cost_of_sales),
            "net_income": float(net_income),
            "margin_pct": float(margin_pct),
        }

    async def build_cash_flow_statement(self, period: str) -> dict[str, object]:
        """
        P3-01: Cash Flow Statement (Direct Method).
        Analyzes all journal entries involving the cash account (1001).
        """
        start_date, end_date = get_period_bounds(period)
        
        # Query all lines for the cash account in the period
        stmt = (
            select(JournalEntryLine.journal_id, JournalEntryLine.debit_amount, JournalEntryLine.credit_amount)
            .join(LedgerAccount, LedgerAccount.id == JournalEntryLine.account_id)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_id)
            .where(LedgerAccount.account_code == ACCOUNT_CODES["cash"])
            .where(JournalEntry.entry_date >= start_date, JournalEntry.entry_date <= end_date)
        )
        cash_lines = (await self.db.execute(stmt)).all()
        
        # For each cash movement, find the counterparty lines to categorize
        operating = Decimal("0.00")
        investing = Decimal("0.00")
        financing = Decimal("0.00")
        
        # To avoid multiple queries, fetch all counterparties for these journals
        journal_ids = {line.journal_id for line in cash_lines}
        if not journal_ids:
            return {
                "period": period,
                "operating": 0.0,
                "investing": 0.0,
                "financing": 0.0,
                "net_cash_flow": 0.0,
            }

        counter_stmt = (
            select(JournalEntryLine.journal_id, LedgerAccount.account_code, JournalEntryLine.debit_amount, JournalEntryLine.credit_amount)
            .join(LedgerAccount, LedgerAccount.id == JournalEntryLine.account_id)
            .where(JournalEntryLine.journal_id.in_(list(journal_ids)))
            .where(LedgerAccount.account_code != ACCOUNT_CODES["cash"])
        )
        counter_lines = (await self.db.execute(counter_stmt)).all()
        
        # Map journal_id to its counterparty accounts
        journal_counters: dict[int, list[tuple[str, Decimal, Decimal]]] = {}
        for row in counter_lines:
            journal_counters.setdefault(row.journal_id, []).append((row.account_code, row.debit_amount, row.credit_amount))
            
        for cash_line in cash_lines:
            net_cash = Decimal(str(cash_line.debit_amount)) - Decimal(str(cash_line.credit_amount))
            counters = journal_counters.get(cash_line.journal_id, [])
            if not counters:
                continue
            
            # Use the first counterparty for categorization (simplified)
            counter_code, _, _ = counters[0]
            
            if counter_code in {ACCOUNT_CODES["ar_installments"], ACCOUNT_CODES["cogs_merchant_payment"], 
                               ACCOUNT_CODES["gateway_fees"], ACCOUNT_CODES["charity_payable"],
                               ACCOUNT_CODES["murabaha_profit"], ACCOUNT_CODES["late_fee_collections"]}:
                operating += net_cash
            elif counter_code in {ACCOUNT_CODES["vcn_issued"], ACCOUNT_CODES["vcn_issuance"]}:
                investing += net_cash
            elif counter_code in {ACCOUNT_CODES["customer_deposits"], ACCOUNT_CODES["owner_equity"]}:
                financing += net_cash
            else:
                # Default to operating for unknown counterparties
                operating += net_cash
                
        return {
            "period": period,
            "operating": float(operating),
            "investing": float(investing),
            "financing": float(financing),
            "net_cash_flow": float(operating + investing + financing),
        }

    async def get_trial_balance(self, period: str) -> dict[str, object]:
        # P1-04: Trial Balance hierarchy support using BalanceService
        _, end_date = get_period_bounds(period)
        
        stmt = select(LedgerAccount).order_by(LedgerAccount.account_code.asc())
        accounts = (await self.db.execute(stmt)).scalars().all()
        
        entries: list[dict[str, object]] = []
        total_debit = Decimal("0.00")
        total_credit = Decimal("0.00")
        
        for account in accounts:
            balance_data = await self.balance_service.get_account_balance(account.account_code, as_of=end_date)
            debit = Decimal(str(balance_data["debit_total"]))
            credit = Decimal(str(balance_data["credit_total"]))
            
            # Skip accounts with zero balance if they are not control accounts
            if debit == 0 and credit == 0 and not account.is_control:
                continue
                
            total_debit += debit
            total_credit += credit
            entries.append(
                {
                    "account_code": account.account_code,
                    "account_name": account.account_name,
                    "account_type": account.account_type,
                    "is_control": bool(account.is_control),
                    "debit_total": float(debit),
                    "credit_total": float(credit),
                    "balance": float(balance_data["balance"]),
                }
            )

        return {
            "period": period,
            "as_of": end_date.isoformat(),
            "entries": entries,
            "total_debit": float(total_debit),
            "total_credit": float(total_credit),
            "is_balanced": total_debit == total_credit,
        }

    async def build_balance_sheet(self, as_of: str | None = None) -> dict[str, object]:
        # P1-04: Balance Sheet hierarchy support using BalanceService
        as_of_date = date.fromisoformat(as_of) if as_of else date.today()

        async def get_accounts_by_type(acc_type: str) -> list[dict[str, object]]:
            stmt = select(LedgerAccount).where(LedgerAccount.account_type == acc_type).order_by(LedgerAccount.account_code.asc())
            accounts = (await self.db.execute(stmt)).scalars().all()
            results = []
            for acc in accounts:
                balance_data = await self.balance_service.get_account_balance(acc.account_code, as_of=as_of_date)
                if balance_data["balance"] == 0 and not acc.is_control:
                    continue
                results.append(
                    {
                        "account_code": acc.account_code,
                        "account_name": acc.account_name,
                        "is_control": bool(acc.is_control),
                        "balance": float(balance_data["balance"]),
                    }
                )
            return results

        assets = await get_accounts_by_type("asset")
        liabilities = await get_accounts_by_type("liability")
        equity = await get_accounts_by_type("equity")

        total_assets = sum((a["balance"] for a in assets if not a["is_control"]), 0.0)
        total_liabilities = sum((l["balance"] for l in liabilities if not l["is_control"]), 0.0)
        total_equity = sum((e["balance"] for e in equity if not e["is_control"]), 0.0)

        total_liabilities_and_equity = total_liabilities + total_equity

        return {
            "as_of": as_of_date.isoformat(),
            "assets": assets,
            "liabilities": liabilities,
            "equity": equity,
            "total_assets": float(total_assets),
            "total_liabilities_and_equity": float(total_liabilities_and_equity),
            "is_balanced": round(total_assets, 2) == round(total_liabilities_and_equity, 2),
        }

    async def list_accounts(self, account_type: str | None = None, as_of: str | None = None) -> dict[str, object]:
        as_of_date = date.fromisoformat(as_of) if as_of else date.today()
        allowed_account_types = {"asset", "liability", "equity", "revenue", "expense"}
        if account_type is not None and account_type not in allowed_account_types:
            raise ValueError("INVALID_ACCOUNT_TYPE")

        stmt = select(LedgerAccount).order_by(LedgerAccount.account_code.asc())
        if account_type is not None:
            stmt = stmt.where(LedgerAccount.account_type == account_type)

        accounts = (await self.db.execute(stmt)).scalars().all()
        items: list[dict[str, object]] = []
        for account in accounts:
            # P1-01: Use BalanceService for accurate rollups and snapshot utilization
            balance_data = await self.balance_service.get_account_balance(account.account_code, as_of=as_of_date)
            items.append(balance_data)

        return {
            "as_of": as_of_date.isoformat(),
            "account_type_filter": account_type,
            "items": items,
        }

    async def get_account_balance(self, account_code: str, as_of: str | None = None) -> dict[str, object]:
        as_of_date = date.fromisoformat(as_of) if as_of else date.today()
        return await self.balance_service.get_account_balance(account_code, as_of=as_of_date)

    async def list_journal_entries(
        self,
        *,
        from_date: str | None = None,
        to_date: str | None = None,
        entry_type: str | None = None,
        source_type: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, object]:
        parsed_from_date = date.fromisoformat(from_date) if from_date else None
        parsed_to_date = date.fromisoformat(to_date) if to_date else None

        stmt = (
            select(JournalEntry)
            .options(selectinload(JournalEntry.lines).selectinload(JournalEntryLine.account))
            .order_by(JournalEntry.entry_number.desc())
        )
        if parsed_from_date is not None:
            stmt = stmt.where(JournalEntry.entry_date >= parsed_from_date)
        if parsed_to_date is not None:
            stmt = stmt.where(JournalEntry.entry_date <= parsed_to_date)
        if entry_type is not None:
            stmt = stmt.where(JournalEntry.entry_type == entry_type)
        if source_type is not None:
            stmt = stmt.where(JournalEntry.source_type == source_type)
        if cursor is not None:
            stmt = stmt.where(JournalEntry.entry_number < cursor)

        rows = (await self.db.execute(stmt.limit(limit + 1))).scalars().all()
        has_more = len(rows) > limit
        entries = rows[:limit]
        next_cursor = entries[-1].entry_number if has_more and entries else None

        items: list[dict[str, object]] = []
        for entry in entries:
            lines: list[dict[str, object]] = []
            for line in entry.lines:
                lines.append(
                    {
                        "account_code": line.account.account_code,
                        "account_name": line.account.account_name,
                        "debit_amount": float(self._money(line.debit_amount)),
                        "credit_amount": float(self._money(line.credit_amount)),
                        "description": line.description,
                    }
                )

            items.append(
                {
                    "entry_number": entry.entry_number,
                    "entry_date": entry.entry_date.isoformat(),
                    "entry_type": entry.entry_type,
                    "source_type": entry.source_type,
                    "source_id": entry.source_id,
                    "description": entry.description,
                    "total_debit": float(self._money(entry.total_debit)),
                    "total_credit": float(self._money(entry.total_credit)),
                    "is_balanced": bool(entry.is_balanced),
                    "lines": lines,
                }
            )

        return {
            "filters": {
                "from_date": from_date,
                "to_date": to_date,
                "entry_type": entry_type,
                "source_type": source_type,
            },
            "pagination": {
                "limit": limit,
                "next_cursor": next_cursor,
                "has_more": has_more,
            },
            "items": items,
        }

    async def get_journal_entry(self, entry_number: str) -> dict[str, object]:
        stmt = (
            select(JournalEntry)
            .options(selectinload(JournalEntry.lines).selectinload(JournalEntryLine.account))
            .where(JournalEntry.entry_number == entry_number)
        )
        entry = (await self.db.execute(stmt)).scalar_one_or_none()
        if entry is None:
            raise LookupError("ENTRY_NOT_FOUND")

        lines: list[dict[str, object]] = []
        for line in entry.lines:
            lines.append(
                {
                    "account_code": line.account.account_code,
                    "account_name": line.account.account_name,
                    "debit_amount": float(self._money(line.debit_amount)),
                    "credit_amount": float(self._money(line.credit_amount)),
                    "description": line.description,
                }
            )

        return {
            "entry_number": entry.entry_number,
            "entry_date": entry.entry_date.isoformat(),
            "entry_type": entry.entry_type,
            "source_type": entry.source_type,
            "source_id": entry.source_id,
            "description": entry.description,
            "total_debit": float(self._money(entry.total_debit)),
            "total_credit": float(self._money(entry.total_credit)),
            "is_balanced": bool(entry.is_balanced),
            "lines": lines,
        }

    @readonly_guard
    async def build_ar_aging_report(
        self,
        *,
        as_of: str | None = None,
        user_id: int | None = None,
        plan_type: str | None = None,
        status: str | None = None,
    ) -> dict[str, object]:
        as_of_date = date.fromisoformat(as_of) if as_of else date.today()

        stmt = (
            select(
                Installment.user_id,
                Installment.loan_id,
                Installment.total_amount,
                Installment.paid_amount,
                Installment.due_date,
                Installment.status,
                Loan.plan_type,
            )
            .join(Loan, Loan.id == Installment.loan_id)
            .where(Installment.deleted_at.is_(None))
            .where(Installment.due_date <= as_of_date)
        )
        if user_id is not None:
            stmt = stmt.where(Installment.user_id == user_id)
        if plan_type is not None:
            stmt = stmt.where(Loan.plan_type == plan_type)
        if status is not None:
            stmt = stmt.where(Installment.status == status)

        rows = (await self.db.execute(stmt)).all()

        buckets: dict[str, dict[str, object]] = {
            "0_30": {"bucket": "0-30", "count": 0, "total_amount": Decimal("0.00")},
            "31_60": {"bucket": "31-60", "count": 0, "total_amount": Decimal("0.00")},
            "61_90": {"bucket": "61-90", "count": 0, "total_amount": Decimal("0.00")},
            "90_plus": {"bucket": "90+", "count": 0, "total_amount": Decimal("0.00")},
        }

        total_outstanding = Decimal("0.00")
        for row in rows:
            outstanding = self._money(row.total_amount) - self._money(row.paid_amount)
            if outstanding <= Decimal("0.00"):
                continue

            days_overdue = max((as_of_date - row.due_date).days, 0)
            if days_overdue <= 30:
                key = "0_30"
            elif days_overdue <= 60:
                key = "31_60"
            elif days_overdue <= 90:
                key = "61_90"
            else:
                key = "90_plus"

            buckets[key]["count"] = int(buckets[key]["count"]) + 1
            buckets[key]["total_amount"] = Decimal(str(buckets[key]["total_amount"])) + outstanding
            total_outstanding += outstanding

        items = [
            {
                "bucket": bucket["bucket"],
                "count": int(bucket["count"]),
                "total_amount": float(self._money(bucket["total_amount"])),
            }
            for bucket in buckets.values()
        ]

        return {
            "as_of": as_of_date.isoformat(),
            "filters": {
                "user_id": user_id,
                "plan_type": plan_type,
                "status": status,
            },
            "items": items,
            "total_outstanding": float(self._money(total_outstanding)),
        }

    @readonly_guard
    async def get_ar_aging_details(
        self,
        *,
        as_of: str | None = None,
        min_days_overdue: int = 0,
        limit: int = 1000,
    ) -> list[dict[str, object]]:
        """
        P3-02: AR aging detail export.
        Returns granular data for each outstanding installment.
        """
        as_of_date = date.fromisoformat(as_of) if as_of else date.today()
        
        stmt = (
            select(
                Installment.id,
                Installment.user_id,
                Installment.loan_id,
                Installment.due_date,
                Installment.amount,
                Installment.paid_amount,
                Loan.plan_type,
            )
            .join(Loan, Loan.id == Installment.loan_id)
            .where(Installment.deleted_at.is_(None))
            .where(Installment.status.in_(["pending", "overdue"]))
            .where(Installment.amount > Installment.paid_amount)
            .order_by(Installment.due_date.asc())
            .limit(limit)
        )
        
        rows = (await self.db.execute(stmt)).all()
        details = []
        for row in rows:
            outstanding = self._money(row.amount) - self._money(row.paid_amount)
            days_overdue = max((as_of_date - row.due_date).days, 0)
            
            if days_overdue < min_days_overdue:
                continue
                
            details.append(
                {
                    "installment_id": row.id,
                    "user_id": row.user_id,
                    "loan_id": row.loan_id,
                    "plan_type": row.plan_type,
                    "due_date": row.due_date.isoformat(),
                    "days_overdue": days_overdue,
                    "outstanding_amount": float(outstanding),
                }
            )
            
        return details

    async def build_shariah_audit_report(self, period: str) -> dict[str, object]:
        start_date, end_date = get_period_bounds(period)

        charity_stmt = (
            select(func.coalesce(func.sum(LateFeeCharityAllocation.late_fee_amount), 0), func.count(LateFeeCharityAllocation.id))
            .where(LateFeeCharityAllocation.deleted_at.is_(None))
            .where(func.date(LateFeeCharityAllocation.allocated_at) >= start_date)
            .where(func.date(LateFeeCharityAllocation.allocated_at) <= end_date)
        )
        allocated_amount, allocation_count = (await self.db.execute(charity_stmt)).one()

        collected_stmt = (
            select(func.coalesce(func.sum(JournalEntryLine.credit_amount), 0))
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_id)
            .join(LedgerAccount, LedgerAccount.id == JournalEntryLine.account_id)
            .where(JournalEntry.entry_date >= start_date, JournalEntry.entry_date <= end_date)
            .where(JournalEntry.source_type == "installment.late_fee")
            .where(LedgerAccount.account_code == ACCOUNT_CODES["charity_payable"])
        )
        collected_amount = Decimal(str((await self.db.execute(collected_stmt)).scalar_one()))
        allocated_decimal = Decimal(str(allocated_amount))
        if collected_amount == Decimal("0"):
            routing_ratio = Decimal("100.0")
        else:
            routing_ratio = (allocated_decimal / collected_amount) * Decimal("100")

        return {
            "period": period,
            "late_fees_allocated": float(allocated_decimal),
            "allocations_count": int(allocation_count),
            "charity_routing_ratio": float(routing_ratio.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        }

    async def _create_balanced_entry(
        self,
        *,
        entry_type: str,
        source_type: str,
        source_id: int | str,
        description: str,
        lines: Iterable[PostingLine],
        entry_date: date | None = None,
    ) -> JournalEntryResult:
        """
        Core posting engine: validates, balances, and persists a journal entry.
        Enforces period closing rules and idempotency via source_type/source_id.
        """
        validate_entry_metadata(entry_type, source_type, source_id)
        
        # Check for existing entry (idempotency)
        existing_stmt = (
            select(JournalEntry)
            .options(selectinload(JournalEntry.lines))
            .where(JournalEntry.source_type == source_type, JournalEntry.source_id == source_id)
        )
        existing = (await self.db.execute(existing_stmt)).scalar_one_or_none()
        if existing is not None:
            return JournalEntryResult(journal_entry=existing, created=False)

        target_date = entry_date or date.today()
        
        # 1. Enforce period is open
        period_key = await self.period_service.ensure_period_open(target_date)
        
        # 2. Validate and balance lines (Domain Layer)
        normalized_lines = list(lines)
        total_debit, total_credit, entry_currency = assert_balanced(normalized_lines)

        # 3. Create entry with sequential number
        entry = JournalEntry(
            entry_number=await self._next_entry_number(target_date),
            entry_date=target_date,
            period_key=period_key,
            description=description,
            entry_type=entry_type,
            source_type=source_type,
            source_id=source_id,
            is_balanced=True,
            total_debit=total_debit,
            total_credit=total_credit,
            currency=entry_currency,
        )
        self.db.add(entry)
        await self.db.flush()

        # 4. Resolve accounts and create lines
        accounts = await self._resolve_accounts({line.account_code for line in normalized_lines})
        for line in normalized_lines:
            account = accounts[line.account_code]
            self.db.add(
                JournalEntryLine(
                    journal_id=entry.id,
                    account_id=account.id,
                    debit_amount=line.debit_amount,
                    credit_amount=line.credit_amount,
                    currency=line.currency,
                    description=line.description,
                )
            )

        await self.db.refresh(entry)
        
        # P0-04: Emit outbound event for downstream services
        if self.publisher:
            await self.publisher.publish_journal_posted(
                entry_id=entry.id,
                entry_number=entry.entry_number,
                payload={
                    "entry_type": entry.entry_type,
                    "source_type": entry.source_type,
                    "source_id": entry.source_id,
                    "total_debit": float(entry.total_debit),
                    "total_credit": float(entry.total_credit),
                },
            )
            
        return JournalEntryResult(journal_entry=entry, created=True)

    async def _resolve_accounts(self, account_codes: set[str]) -> dict[str, LedgerAccount]:
        if not account_codes:
            return {}
        stmt = select(LedgerAccount).where(LedgerAccount.account_code.in_(sorted(account_codes)))
        rows = (await self.db.execute(stmt)).scalars().all()
        found = {row.account_code: row for row in rows}
        missing = sorted(account_codes - set(found))
        if missing:
            raise LookupError(f"Missing ledger accounts: {', '.join(missing)}")
        return found

    async def _get_installment(self, installment_id: int) -> Installment:
        stmt = select(Installment).where(Installment.id == installment_id)
        installment = (await self.db.execute(stmt)).scalar_one_or_none()
        if installment is None:
            raise LookupError(f"Installment {installment_id} not found")
        return installment

    async def _get_default_charity_org(self) -> CharityOrganization:
        stmt = select(CharityOrganization).where(CharityOrganization.is_active.is_(True)).order_by(CharityOrganization.id.asc())
        charity_org = (await self.db.execute(stmt)).scalars().first()
        if charity_org is None:
            raise LookupError("No active charity organization configured")
        return charity_org

    async def _next_entry_number(self, target_date: date) -> str:
        """
        Generate a sequential entry number. 
        P0-06: In production (Postgres), we MUST use the sequence to ensure gaps are visible and duplicates are impossible.
        """
        from sqlalchemy import text
        bind = self.db.get_bind()
        
        if bind.dialect.name == "postgresql":
            # Using nextval ensures atomicity and sequential integrity.
            # If this fails, we WANT the transaction to fail rather than using an unsafe UUID fallback.
            result = await self.db.execute(text("SELECT nextval('journal_entry_number_seq')"))
            seq_val = result.scalar()
            return f"JE-{target_date.strftime('%Y%m')}-{seq_val:06d}"
        
        # Fallback for non-postgres (sqlite in tests)
        return f"JE-{target_date.strftime('%Y%m')}-{uuid4().hex[:6].upper()}"

    def _money(self, value: Decimal | float | int) -> Decimal:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)