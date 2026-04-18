from __future__ import annotations

from datetime import date
from datetime import datetime, timezone
from decimal import Decimal
import json
import logging
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.payment import PaymentTransaction
from src.config import settings


logger = logging.getLogger(__name__)


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

        if matched_ids:
            await self.db.execute(
                update(PaymentTransaction)
                .where(PaymentTransaction.id.in_(matched_ids))
                .values(reconciled_at=now)
                .execution_options(synchronize_session=False)
            )
            await self.db.commit()

        discrepancy = actual_decimal - expected_decimal
        status = "matched" if discrepancy == Decimal("0") else "variance"

        snapshot_id = uuid4().hex
        snapshot_record = {
            "snapshot_id": snapshot_id,
            "created_at": now.isoformat(),
            "gateway": gateway,
            "settlement_date": settlement_date,
            "expected_amount": str(expected_decimal),
            "actual_amount": str(actual_decimal),
            "matched_transaction_count": len(matched_ids),
            "matched_transaction_amount": str(matched_amount),
            "discrepancy": str(discrepancy),
            "reference": reference,
            "notes": notes,
            "status": status,
        }
        await self._append_jsonl(self._snapshots_path(), snapshot_record)

        for txn_id in matched_ids:
            await self._append_jsonl(
                self._items_path(),
                {
                    "item_id": uuid4().hex,
                    "snapshot_id": snapshot_id,
                    "transaction_id": txn_id,
                    "gateway_ref": reference,
                    "item_status": "matched",
                    "created_at": now.isoformat(),
                },
            )

        if discrepancy != Decimal("0"):
            await self._append_jsonl(
                self._items_path(),
                {
                    "item_id": uuid4().hex,
                    "snapshot_id": snapshot_id,
                    "transaction_id": None,
                    "gateway_ref": reference,
                    "item_status": "discrepancy",
                    "discrepancy_amount": str(discrepancy),
                    "created_at": now.isoformat(),
                },
            )

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

        records = await self._load_snapshots()
        filtered = [
            record
            for record in records
            if (not gateway or record.get("gateway") == gateway)
            and (not settlement_date or record.get("settlement_date") == settlement_date)
        ]

        filtered.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        total = len(filtered)
        start = (page - 1) * limit
        end = start + limit
        page_rows = filtered[start:end]

        items = []
        for row in page_rows:
            items.append(
                {
                    "gateway": row.get("gateway"),
                    "settlement_id": None,
                    "transaction_count": int(row.get("matched_transaction_count", 0)),
                    "total_amount": float(Decimal(str(row.get("matched_transaction_amount", "0")))),
                    "last_reconciled_at": self._parse_iso_datetime(row.get("created_at")),
                }
            )

        total_count = sum(int(row.get("matched_transaction_count", 0)) for row in filtered)
        total_amount = sum((Decimal(str(row.get("matched_transaction_amount", "0"))) for row in filtered), Decimal("0.00"))

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
                "transaction_count": int(total_count),
                "total_amount": float(total_amount),
            },
        }

    async def _load_snapshots(self) -> list[dict[str, object]]:
        path = self._snapshots_path()
        if not path.exists():
            return []

        rows: list[dict[str, object]] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                payload = json.loads(stripped)
                if isinstance(payload, dict):
                    rows.append(payload)
        except Exception:
            logger.exception("Failed to load reconciliation snapshots", extra={"path": str(path)})
            raise
        return rows

    async def _append_jsonl(self, path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":"), default=str))
            handle.write("\n")

    def _audit_root(self) -> Path:
        return Path(settings.reconciliation_audit_dir)

    def _snapshots_path(self) -> Path:
        return self._audit_root() / "reconciliation_snapshots.jsonl"

    def _items_path(self) -> Path:
        return self._audit_root() / "reconciliation_items.jsonl"

    def _parse_iso_datetime(self, value: object) -> datetime | None:
        if not value or not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _utc_now(self) -> datetime:
        return datetime.now(timezone.utc)