from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.payment import PaymentTransaction


class ReconciliationService:
    def __init__(self, db_session: AsyncSession) -> None:
        self.db = db_session

    async def import_snapshot(
        self,
        *,
        gateway: str,
        settlement_date: str,
        expected_amount: Decimal,
        actual_amount: Decimal,
        reference: str | None = None,
        notes: str | None = None,
    ) -> dict[str, object]:
        discrepancy = actual_amount - expected_amount
        return {
            "gateway": gateway,
            "settlement_date": settlement_date,
            "expected_amount": float(expected_amount),
            "actual_amount": float(actual_amount),
            "discrepancy": float(discrepancy),
            "reference": reference,
            "notes": notes,
            "status": "queued",
        }

    async def query_snapshots(
        self,
        *,
        gateway: str | None = None,
        settlement_date: str | None = None,
        page: int = 1,
        limit: int = 50,
    ) -> dict[str, object]:
        filters = [PaymentTransaction.deleted_at.is_(None)]
        if gateway:
            filters.append(PaymentTransaction.gateway == gateway)

        if settlement_date:
            target_date = date.fromisoformat(settlement_date)
            filters.append(func.date(PaymentTransaction.reconciled_at) == target_date)

        stmt = (
            select(
                PaymentTransaction.gateway.label("gateway"),
                PaymentTransaction.settlement_id.label("settlement_id"),
                func.count(PaymentTransaction.id).label("transaction_count"),
                func.coalesce(func.sum(PaymentTransaction.amount), 0).label("total_amount"),
                func.max(PaymentTransaction.reconciled_at).label("last_reconciled_at"),
            )
            .where(*filters)
            .group_by(PaymentTransaction.gateway, PaymentTransaction.settlement_id)
            .order_by(func.max(PaymentTransaction.reconciled_at).desc().nullslast())
            .limit(limit)
            .offset((page - 1) * limit)
        )

        count_stmt = select(func.count()).select_from(PaymentTransaction).where(*filters)
        totals_stmt = (
            select(
                func.coalesce(func.count(PaymentTransaction.id), 0),
                func.coalesce(func.sum(PaymentTransaction.amount), 0),
            )
            .where(*filters)
        )

        try:
            rows = (await self.db.execute(stmt)).mappings().all()
            total = int((await self.db.execute(count_stmt)).scalar_one())
            total_count, total_amount = (await self.db.execute(totals_stmt)).one()
        except Exception:
            rows = []
            total = 0
            total_count, total_amount = 0, 0

        items = [
            {
                "gateway": row["gateway"],
                "settlement_id": row["settlement_id"],
                "transaction_count": int(row["transaction_count"] or 0),
                "total_amount": float(row["total_amount"] or 0),
                "last_reconciled_at": row["last_reconciled_at"],
            }
            for row in rows
        ]

        return {
            "filters": {
                "gateway": gateway,
                "settlement_date": settlement_date,
            },
            "items": items,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
            },
            "summary": {
                "transaction_count": int(total_count or 0),
                "total_amount": float(total_amount or 0),
            },
        }