from __future__ import annotations

from datetime import date
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.payment import PaymentTransaction, Reconciliation, ReconciliationItem
from src.core.readonly_guard import readonly_guard


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
        target_date = date.fromisoformat(settlement_date)
        expected_decimal = Decimal(str(expected_amount))
        actual_decimal = Decimal(str(actual_amount))

        matched_stmt = (
            select(PaymentTransaction.id, PaymentTransaction.amount)
            .where(PaymentTransaction.deleted_at.is_(None))
            .where(PaymentTransaction.gateway == gateway)
            .where(func.date(PaymentTransaction.created_at) == target_date)
        )
        matched_rows = (await self.db.execute(matched_stmt)).all()
        matched_ids = [int(row[0]) for row in matched_rows]
        matched_amount = sum((Decimal(str(row[1])) for row in matched_rows), Decimal("0.00"))
        now = self._utc_now()

        discrepancy = actual_decimal - expected_decimal
        status = "matched" if discrepancy == Decimal("0") else "discrepant"

        from src.core.period_utils import get_period_key
        reconciliation = Reconciliation(
            gateway=gateway,
            settlement_date=target_date,
            expected_amount=expected_decimal,
            actual_amount=actual_decimal,
            status=status,
            period_key=get_period_key(target_date),
            reconciled_at=now,
            notes=notes,
        )
        self.db.add(reconciliation)
        await self.db.flush()

        for txn in matched_rows:
            txn_id = int(txn[0])
            txn_amount = Decimal(str(txn[1]))
            self.db.add(
                ReconciliationItem(
                    reconciliation_id=reconciliation.id,
                    payment_txn_id=txn_id,
                    gateway_ref=reference,
                    expected_amount=txn_amount,
                    actual_amount=txn_amount,
                    status="matched",
                    created_at=now,
                )
            )

        if discrepancy != Decimal("0"):
            self.db.add(
                ReconciliationItem(
                    reconciliation_id=reconciliation.id,
                    payment_txn_id=None,
                    gateway_ref=reference,
                    expected_amount=expected_decimal,
                    actual_amount=actual_decimal,
                    status="discrepant",
                    discrepancy_note=f"Discrepancy amount: {discrepancy}",
                    created_at=now,
                )
            )

        if matched_ids:
            await self.db.execute(
                update(PaymentTransaction)
                .where(PaymentTransaction.id.in_(matched_ids))
                .values(reconciled_at=now, settlement_id=reconciliation.id)
                .execution_options(synchronize_session=False)
            )

        await self.db.commit()

        return {
            "gateway": gateway,
            "settlement_date": settlement_date,
            "expected_amount": float(expected_decimal),
            "actual_amount": float(actual_decimal),
            "matched_transaction_count": len(matched_ids),
            "matched_transaction_amount": float(matched_amount),
            "discrepancy": float(discrepancy),
            "reference": reference,
            "notes": notes,
            "status": status,
        }

    @readonly_guard
    async def query_snapshots(
        self,
        *,
        gateway: str | None = None,
        settlement_date: str | None = None,
        page: int = 1,
        limit: int = 50,
    ) -> dict[str, object]:
        if settlement_date:
            date.fromisoformat(settlement_date)

        filters = []
        if gateway:
            filters.append(Reconciliation.gateway == gateway)
        if settlement_date:
            filters.append(Reconciliation.settlement_date == date.fromisoformat(settlement_date))

        totals_subquery = (
            select(
                ReconciliationItem.reconciliation_id.label("reconciliation_id"),
                func.coalesce(func.sum(case((ReconciliationItem.status == "matched", 1), else_=0)), 0).label("transaction_count"),
                func.coalesce(
                    func.sum(
                        case(
                            (ReconciliationItem.status == "matched", ReconciliationItem.actual_amount),
                            else_=Decimal("0.00"),
                        )
                    ),
                    0,
                ).label("total_amount"),
            )
            .group_by(ReconciliationItem.reconciliation_id)
            .subquery()
        )

        total_stmt = select(func.count(Reconciliation.id))
        if filters:
            total_stmt = total_stmt.where(*filters)
        total = int((await self.db.execute(total_stmt)).scalar_one())

        stmt = (
            select(
                Reconciliation.id,
                Reconciliation.gateway,
                Reconciliation.reconciled_at,
                func.coalesce(totals_subquery.c.transaction_count, 0).label("transaction_count"),
                func.coalesce(totals_subquery.c.total_amount, 0).label("total_amount"),
            )
            .outerjoin(totals_subquery, totals_subquery.c.reconciliation_id == Reconciliation.id)
            .order_by(Reconciliation.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        if filters:
            stmt = stmt.where(*filters)

        rows = (await self.db.execute(stmt)).all()

        items: list[dict[str, object]] = []
        for row in rows:
            items.append(
                {
                    "gateway": row.gateway,
                    "settlement_id": int(row.id),
                    "transaction_count": int(row.transaction_count or 0),
                    "total_amount": float(Decimal(str(row.total_amount or 0))),
                    "last_reconciled_at": row.reconciled_at,
                }
            )

        summary_stmt = select(
            func.coalesce(func.sum(totals_subquery.c.transaction_count), 0),
            func.coalesce(func.sum(totals_subquery.c.total_amount), 0),
        ).select_from(Reconciliation).outerjoin(
            totals_subquery, totals_subquery.c.reconciliation_id == Reconciliation.id
        )
        if filters:
            summary_stmt = summary_stmt.where(*filters)
        summary_count, summary_amount = (await self.db.execute(summary_stmt)).one()

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
                "transaction_count": int(summary_count or 0),
                "total_amount": float(Decimal(str(summary_amount or 0))),
            },
        }

    def _utc_now(self) -> datetime:
        return datetime.now(timezone.utc)