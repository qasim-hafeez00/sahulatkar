from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sk_shared.models.ledger import CharityOrganization, JournalEntry, JournalEntryLine, LateFeeCharityAllocation, LedgerAccount
from sk_shared.models.payment import Installment

from src.accounting.accounts import ACCOUNT_CODES, PostingLine


@dataclass(slots=True)
class JournalEntryResult:
    journal_entry: JournalEntry
    created: bool


class AccountingService:
    def __init__(self, db_session: AsyncSession) -> None:
        self.db = db_session

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

    async def build_profit_loss_report(self, period: str) -> dict[str, object]:
        revenue_accounts = {ACCOUNT_CODES["murabaha_profit"], ACCOUNT_CODES["affiliate_commission"], ACCOUNT_CODES["late_fee_collections"]}
        expense_accounts = {ACCOUNT_CODES["cogs_merchant_payment"], ACCOUNT_CODES["gateway_fees"], ACCOUNT_CODES["vcn_issuance"], ACCOUNT_CODES["loan_loss_provision"]}

        revenue_stmt = (
            select(func.coalesce(func.sum(JournalEntryLine.credit_amount), 0), func.coalesce(func.sum(JournalEntryLine.debit_amount), 0))
            .join(LedgerAccount, LedgerAccount.id == JournalEntryLine.account_id)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_id)
            .where(LedgerAccount.account_code.in_(revenue_accounts))
        )
        expense_stmt = (
            select(func.coalesce(func.sum(JournalEntryLine.debit_amount), 0))
            .join(LedgerAccount, LedgerAccount.id == JournalEntryLine.account_id)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_id)
            .where(LedgerAccount.account_code.in_(expense_accounts))
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

    async def build_shariah_audit_report(self, period: str) -> dict[str, object]:
        charity_stmt = select(func.coalesce(func.sum(LateFeeCharityAllocation.late_fee_amount), 0), func.count(LateFeeCharityAllocation.id)).where(
            LateFeeCharityAllocation.deleted_at.is_(None)
        )
        allocated_amount, allocation_count = (await self.db.execute(charity_stmt)).one()
        return {
            "period": period,
            "late_fees_allocated": float(Decimal(str(allocated_amount))),
            "allocations_count": int(allocation_count),
            "charity_routing_ratio": 100.0,
        }

    async def _create_balanced_entry(
        self,
        *,
        entry_type: str,
        source_type: str,
        source_id: int,
        description: str,
        lines: Iterable[PostingLine],
    ) -> JournalEntryResult:
        existing_stmt = (
            select(JournalEntry)
            .options(selectinload(JournalEntry.lines))
            .where(JournalEntry.source_type == source_type, JournalEntry.source_id == source_id)
        )
        existing = (await self.db.execute(existing_stmt)).scalar_one_or_none()
        if existing is not None:
            return JournalEntryResult(journal_entry=existing, created=False)

        normalized_lines = list(lines)
        total_debit = sum((line.debit_amount for line in normalized_lines), Decimal("0.00"))
        total_credit = sum((line.credit_amount for line in normalized_lines), Decimal("0.00"))
        if total_debit != total_credit:
            raise ValueError("JOURNAL_ENTRY_NOT_BALANCED")

        entry = JournalEntry(
            entry_number=await self._next_entry_number(),
            entry_date=date.today(),
            description=description,
            entry_type=entry_type,
            source_type=source_type,
            source_id=source_id,
            is_balanced=True,
            total_debit=total_debit,
            total_credit=total_credit,
        )
        self.db.add(entry)
        await self.db.flush()

        accounts = await self._resolve_accounts({line.account_code for line in normalized_lines})
        for line in normalized_lines:
            account = accounts[line.account_code]
            self.db.add(
                JournalEntryLine(
                    journal_id=entry.id,
                    account_id=account.id,
                    debit_amount=line.debit_amount,
                    credit_amount=line.credit_amount,
                    description=line.description,
                )
            )

        await self.db.refresh(entry)
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

    async def _next_entry_number(self) -> str:
        entry_date = date.today()
        stmt = select(func.count(JournalEntry.id)).where(JournalEntry.entry_date == entry_date)
        existing_count = int((await self.db.execute(stmt)).scalar_one())
        return f"JE-{entry_date:%Y}-{existing_count + 1:07d}"

    def _money(self, value: Decimal | float | int) -> Decimal:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)