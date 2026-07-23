from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.credit_reason_codes import FlagCode
from sk_shared.models.auth import User
from sk_shared.models.credit import BankStatementAnalysis
from src.adapters.wallet import MockJazzCashAdapter, WalletAdapter
from src.config import settings


@dataclass
class AffordabilityResult:
    wallet_activity_score: float
    income_signal: str
    provider: str
    income_estimate: float | None = None
    debt_to_income_ratio: float | None = None
    flags: list[str] = field(default_factory=list)


class AffordabilityEngine:
    """Blends the live wallet-activity signal (behind WalletAdapter, mock today) with
    bank_statement_analysis — avg_balance, salary_detected, expense_ratio, nsf_events — into
    one affordability score with a debt-to-income read. Formerly layer4_alt_data.py's
    hardcoded mock; the wallet leg is still a mock, but it's isolated behind WalletAdapter so
    a real JazzCash/Easypaisa adapter drops in without touching this engine or the pipeline.
    """

    def __init__(self, wallet_adapter: WalletAdapter | None = None) -> None:
        self.wallet_adapter = wallet_adapter or MockJazzCashAdapter()

    async def evaluate(self, db: AsyncSession, user_id: str) -> AffordabilityResult:
        wallet_score = await self.wallet_adapter.get_activity_score(user_id)
        provider = getattr(self.wallet_adapter, "provider", "wallet-adapter")

        bank_row = await self._latest_bank_statement(db, user_id)
        if bank_row is None:
            return AffordabilityResult(
                wallet_activity_score=round(wallet_score, 2),
                income_signal="unknown",
                provider=provider,
                flags=[FlagCode.BANK_DATA_UNAVAILABLE],
            )

        bank_score, income_signal, bank_flags = self._score_bank_statement(bank_row)
        blended = (
            wallet_score * settings.affordability_wallet_weight
            + bank_score * settings.affordability_bank_weight
        )

        return AffordabilityResult(
            wallet_activity_score=round(blended, 2),
            income_signal=income_signal,
            provider=provider,
            income_estimate=float(bank_row.income_estimate) if bank_row.income_estimate is not None else None,
            debt_to_income_ratio=float(bank_row.expense_ratio) if bank_row.expense_ratio is not None else None,
            flags=bank_flags,
        )

    async def _latest_bank_statement(self, db: AsyncSession, user_id: str) -> BankStatementAnalysis | None:
        try:
            user_uuid = UUID(user_id)
        except ValueError:
            return None
        user_int_id = (await db.execute(select(User.id).where(User.uuid == user_uuid))).scalar_one_or_none()
        if user_int_id is None:
            return None

        stmt = (
            select(BankStatementAnalysis)
            .where(BankStatementAnalysis.user_id == user_int_id)
            .order_by(BankStatementAnalysis.period_end.desc())
            .limit(1)
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    def _score_bank_statement(self, row: BankStatementAnalysis) -> tuple[float, str, list[str]]:
        flags: list[str] = []
        score = 50.0

        if row.salary_detected:
            score += 20.0
            flags.append(FlagCode.SALARY_VERIFIED)

        expense_ratio = float(row.expense_ratio) if row.expense_ratio is not None else None
        if expense_ratio is not None:
            score += max(0.0, 1.0 - expense_ratio) * 30.0
            if expense_ratio > settings.max_debt_to_income_ratio:
                flags.append(FlagCode.HIGH_DEBT_TO_INCOME)

        score -= min(row.nsf_events, 4) * 5.0

        income_estimate = float(row.income_estimate) if row.income_estimate is not None else None
        if income_estimate is not None and income_estimate < settings.min_monthly_income:
            flags.append(FlagCode.INCOME_BELOW_MINIMUM)

        score = min(max(score, 0.0), 100.0)
        if FlagCode.HIGH_DEBT_TO_INCOME in flags or FlagCode.INCOME_BELOW_MINIMUM in flags:
            income_signal = "weak"
        elif row.salary_detected:
            income_signal = "stable"
        else:
            income_signal = "moderate"
        return score, income_signal, flags
