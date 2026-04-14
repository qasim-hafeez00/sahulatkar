from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.payment import Installment


class BillingSweepService:
    def __init__(self, db_session: AsyncSession) -> None:
        self.db = db_session

    async def load_due_installments(self, as_of: date | None = None, limit: int = 500) -> list[Installment]:
        due_date = as_of or date.today()
        stmt = (
            select(Installment)
            .where(Installment.status == "pending", Installment.due_date <= due_date)
            .order_by(Installment.due_date.asc(), Installment.id.asc())
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def plan_daily_sweep(self, as_of: date | None = None, limit: int = 500) -> dict[str, object]:
        installments = await self.load_due_installments(as_of=as_of, limit=limit)
        return {
            "as_of": (as_of or date.today()).isoformat(),
            "due_count": len(installments),
            "installments": [
                {
                    "installment_id": installment.id,
                    "loan_id": installment.loan_id,
                    "due_date": installment.due_date.isoformat(),
                    "status": installment.status,
                    "retry_count": installment.retry_count,
                    "next_retry_at": installment.next_retry_at.isoformat() if installment.next_retry_at else None,
                }
                for installment in installments
            ],
        }

    async def execute_sweep(self, as_of: date | None = None) -> dict[str, int]:
        import httpx
        from src.config import settings
        from src.services.accounting_service import AccountingService

        installments = await self.load_due_installments(as_of=as_of)
        stats = {"total": len(installments), "success": 0, "failed": 0, "already_paid": 0}
        accounting = AccountingService(self.db)

        async with httpx.AsyncClient(timeout=10.0) as client:
            for inst in installments:
                try:
                    resp = await client.post(
                        f"{settings.payment_service_url}/api/v1/payments/internal/trigger-installment",
                        json={"installment_id": inst.id, "method": "jazzcash"} # Trigger auto-debit
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if data["status"] == "success":
                            # Payment was successful, record it in ledger
                            await accounting.record_installment_paid(inst.id, inst.total_amount)
                            stats["success"] += 1
                        elif data["status"] == "already_paid":
                            stats["already_paid"] += 1
                        else:
                            stats["failed"] += 1
                    else:
                        stats["failed"] += 1
                except Exception:
                    stats["failed"] += 1

        return stats