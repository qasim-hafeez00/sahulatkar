from __future__ import annotations

from datetime import date
from datetime import datetime
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.payment import PaymentTransaction, Reconciliation, ReconciliationItem
from sk_shared.redis_client import RedisClient
from src.core.readonly_guard import readonly_guard
from src.events.publisher import EventPublisher


class ReconciliationService:
    def __init__(self, db_session: AsyncSession, redis: RedisClient | None = None) -> None:
        self.db = db_session
        self.publisher = EventPublisher(redis) if redis else None

    async def import_snapshot(
        self,
        *,
        gateway: str,
        settlement_date: str,
        expected_amount: Decimal,
        actual_amount: Decimal,
        reference: str | None = None,
        notes: str | None = None,
        line_items: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        """
        Args:
            line_items: Optional per-transaction settlement records reported
                by the gateway, e.g. [{"gateway_txn_id": "safepay_abc123",
                "amount": Decimal("120.00")}, ...]. When provided, this runs a
                genuine transaction-by-transaction reconciliation check as a
                SUPPLEMENT to the pre-existing aggregate check above: two
                offsetting per-transaction errors (e.g. one transaction
                under-reported by 10, another over-reported by 10) net to
                zero in expected_amount/actual_amount and in matched_amount,
                so the aggregate check alone cannot see them. Comparing each
                gateway-reported line against our own PaymentTransaction
                records line-by-line catches exactly that class of error and
                forces the overall status to "discrepant" even when the
                aggregate totals match. When omitted (the default, and the
                only mode the CLI worker/admin API currently exercise), this
                is a no-op and behavior is unchanged from before.
        """
        target_date = date.fromisoformat(settlement_date)
        expected_decimal = Decimal(str(expected_amount))
        actual_decimal = Decimal(str(actual_amount))

        # INC-08: Paginated matched rows query to avoid OOM
        matched_ids: list[int] = []
        matched_amount = Decimal("0.00")
        offset = 0
        batch_size = 1000

        while True:
            matched_stmt = (
                select(PaymentTransaction.id, PaymentTransaction.amount)
                .where(PaymentTransaction.deleted_at.is_(None))
                .where(PaymentTransaction.gateway == gateway)
                .where(func.date(PaymentTransaction.created_at) == target_date)
                .offset(offset)
                .limit(batch_size)
            )
            batch_rows = (await self.db.execute(matched_stmt)).all()
            if not batch_rows:
                break
            
            for row in batch_rows:
                matched_ids.append(int(row[0]))
                matched_amount += Decimal(str(row[1]))
            
            offset += batch_size

        now = self._utc_now()
        discrepancy = actual_decimal - expected_decimal

        # LS-BL-06: Also compare the sum of matched PaymentTransaction amounts
        # against both expected_amount and actual_amount for true reconciliation.
        matched_vs_expected_discrepancy = matched_amount - expected_decimal
        matched_amount - actual_decimal

        if abs(matched_vs_expected_discrepancy) > Decimal("1.00"):
            reconciliation_note = (
                f"AMOUNT_MISMATCH: matched_txn_sum={matched_amount}, "
                f"expected={expected_decimal}, actual={actual_decimal}. "
                f"Discrepancy vs expected: {matched_vs_expected_discrepancy}. "
                f"Possible missing or duplicate PaymentTransaction records."
            )
            status = "discrepant"
            if notes:
                notes = f"{notes}\n{reconciliation_note}"
            else:
                notes = reconciliation_note
        else:
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

        # BV-02: Redo the loop to keep amounts and create items
        matched_data: list[tuple[int, Decimal]] = []
        local_txns: list[tuple[int, str | None, Decimal]] = []
        offset = 0
        while True:
            stmt = (
                select(PaymentTransaction.id, PaymentTransaction.gateway_txn_id, PaymentTransaction.amount)
                .where(PaymentTransaction.deleted_at.is_(None))
                .where(PaymentTransaction.gateway == gateway)
                .where(func.date(PaymentTransaction.created_at) == target_date)
                .offset(offset)
                .limit(batch_size)
            )
            rows = (await self.db.execute(stmt)).all()
            if not rows:
                break
            for r in rows:
                txn_id, gateway_txn_id, txn_amount = int(r[0]), r[1], Decimal(str(r[2]))
                matched_data.append((txn_id, txn_amount))
                local_txns.append((txn_id, gateway_txn_id, txn_amount))
            offset += batch_size

        # LS-MED-04: Line-level (transaction-by-transaction) reconciliation.
        # Supplements the aggregate expected_amount/actual_amount check above,
        # which cannot see two offsetting per-transaction errors that net to
        # zero. When line_items isn't supplied, this reduces to the original
        # behavior: every local transaction for the gateway/date gets a
        # "matched" ReconciliationItem mirroring itself.
        line_level_mismatches: list[str] = []
        if line_items is None:
            for txn_id, gateway_txn_id, txn_amount in local_txns:
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
        else:
            local_by_gateway_id = {
                gateway_txn_id: (txn_id, txn_amount)
                for txn_id, gateway_txn_id, txn_amount in local_txns
                if gateway_txn_id is not None
            }
            seen_gateway_ids: set[str] = set()

            for item in line_items:
                item_gateway_id = str(item["gateway_txn_id"])
                item_amount = Decimal(str(item["amount"]))
                seen_gateway_ids.add(item_gateway_id)
                local = local_by_gateway_id.get(item_gateway_id)

                if local is None:
                    line_level_mismatches.append(item_gateway_id)
                    self.db.add(
                        ReconciliationItem(
                            reconciliation_id=reconciliation.id,
                            payment_txn_id=None,
                            gateway_ref=item_gateway_id,
                            expected_amount=item_amount,
                            actual_amount=None,
                            status="discrepant",
                            discrepancy_note=(
                                f"Gateway settlement line {item_gateway_id} (amount {item_amount}) "
                                "has no matching local PaymentTransaction."
                            ),
                            created_at=now,
                        )
                    )
                    continue

                local_txn_id, local_amount = local
                if local_amount != item_amount:
                    line_level_mismatches.append(item_gateway_id)
                    self.db.add(
                        ReconciliationItem(
                            reconciliation_id=reconciliation.id,
                            payment_txn_id=local_txn_id,
                            gateway_ref=item_gateway_id,
                            expected_amount=item_amount,
                            actual_amount=local_amount,
                            status="discrepant",
                            discrepancy_note=(
                                f"Line-level amount mismatch for {item_gateway_id}: gateway "
                                f"reports {item_amount}, local record has {local_amount}."
                            ),
                            created_at=now,
                        )
                    )
                else:
                    self.db.add(
                        ReconciliationItem(
                            reconciliation_id=reconciliation.id,
                            payment_txn_id=local_txn_id,
                            gateway_ref=item_gateway_id,
                            expected_amount=item_amount,
                            actual_amount=local_amount,
                            status="matched",
                            created_at=now,
                        )
                    )

            # Local transactions the gateway's settlement file never mentioned.
            for gateway_txn_id, (local_txn_id, local_amount) in local_by_gateway_id.items():
                if gateway_txn_id in seen_gateway_ids:
                    continue
                line_level_mismatches.append(gateway_txn_id)
                self.db.add(
                    ReconciliationItem(
                        reconciliation_id=reconciliation.id,
                        payment_txn_id=local_txn_id,
                        gateway_ref=gateway_txn_id,
                        expected_amount=local_amount,
                        actual_amount=None,
                        status="discrepant",
                        discrepancy_note=(
                            f"Local transaction {gateway_txn_id} (amount {local_amount}) is not "
                            "present in the gateway's settlement line items."
                        ),
                        created_at=now,
                    )
                )

            if line_level_mismatches:
                # BV: Force the overall reconciliation to "discrepant" even if
                # the aggregate expected/actual totals matched -- this is the
                # entire point of the line-level check: it catches offsetting
                # errors the aggregate comparison structurally cannot see.
                status = "discrepant"
                line_note = (
                    "LINE_LEVEL_MISMATCH: transaction-by-transaction check found "
                    f"{len(line_level_mismatches)} discrepant line(s) not visible to the "
                    f"aggregate check: {', '.join(sorted(line_level_mismatches))}"
                )
                notes = f"{notes}\n{line_note}" if notes else line_note
                reconciliation.status = status
                reconciliation.notes = notes

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

        # BV-02: We no longer update PaymentTransaction directly.
        # Instead, we publish an event.
        if self.publisher and matched_data:
            await self.publisher.publish_reconciliation_matched(reconciliation.id, [m[0] for m in matched_data])

        await self.db.commit()

        return {
            "gateway": gateway,
            "settlement_date": settlement_date,
            "expected_amount": float(expected_decimal),
            "actual_amount": float(actual_decimal),
            "matched_transaction_count": len(matched_data),
            "matched_transaction_amount": float(matched_amount),
            "discrepancy": float(discrepancy),
            "reference": reference,
            "notes": notes,
            "status": status,
        }

    async def manual_override(self, reconciliation_id: int, reason: str, admin_user: str) -> dict[str, object]:
        """
        P1-05: Manual reconciliation override API.
        Allows finance admin to force-match a discrepant settlement.
        """
        stmt = select(Reconciliation).where(Reconciliation.id == reconciliation_id)
        reconciliation = (await self.db.execute(stmt)).scalar_one_or_none()
        if not reconciliation:
            raise LookupError("RECONCILIATION_NOT_FOUND")
            
        if reconciliation.status == "matched":
            raise ValueError("ALREADY_MATCHED")
            
        reconciliation.status = "force_matched"
        reconciliation.notes = f"{reconciliation.notes or ''}\n[Override by {admin_user}]: {reason}".strip()
        reconciliation.reconciled_at = self._utc_now()
        
        await self.db.commit()
        await self.db.refresh(reconciliation)
        
        return {
            "reconciliation_id": reconciliation.id,
            "status": reconciliation.status,
            "notes": reconciliation.notes,
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
        return datetime.utcnow()