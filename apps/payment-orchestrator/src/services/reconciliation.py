"""
Payment Reconciliation Service.

Matches gateway settlement records against internal PaymentTransaction records.
This is payment-level reconciliation (did we record what the gateway processed?).
Accounting-level reconciliation lives in the Ledger Service.

Output events:
  - Does not emit pub/sub events — produces structured reports.
  - Reports are stored in JSONL audit files and returned via admin API.

Usage:
  - Triggered by the reconciliation worker on a scheduled cron.
  - Can also be triggered manually via admin API for ad-hoc reconciliation.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.payment import PaymentTransaction

from src.config import settings
from src.schemas.reconciliation import (
    ReconciliationImportRequest,
    ReconciliationItemResult,
    ReconciliationReport,
)

logger = logging.getLogger(__name__)


class ReconciliationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def reconcile(self, request: ReconciliationImportRequest) -> ReconciliationReport:
        """
        Run reconciliation for one gateway's settlement batch.

        Steps:
        1. Fetch all internal PaymentTransactions for the settlement period
        2. For each gateway record, find matching internal transaction by gateway_txn_id
        3. Compare amounts; flag discrepancies
        4. Persist audit JSONL
        5. Return structured report
        """
        gateway = request.gateway
        settlement_date = request.settlement_date

        # ── 1. Load all internal transactions for this gateway ────────────────
        result = await self.db.execute(
            select(PaymentTransaction).where(
                PaymentTransaction.gateway == gateway,
                PaymentTransaction.status == "success",
                PaymentTransaction.deleted_at.is_(None),
            )
        )
        internal_txns: dict[str, PaymentTransaction] = {
            txn.gateway_txn_id: txn
            for txn in result.scalars().all()
            if txn.gateway_txn_id
        }

        # ── 2. Build gateway lookup ───────────────────────────────────────────
        gateway_txns = {r.gateway_txn_id: r for r in request.records}

        # ── 3. Match and identify discrepancies ───────────────────────────────
        items: List[ReconciliationItemResult] = []
        total_gateway_amount = Decimal("0.00")
        total_internal_amount = Decimal("0.00")
        matched = 0
        discrepancies = 0

        # Check all gateway records against internal
        for gw_txn_id, gw_record in gateway_txns.items():
            total_gateway_amount += gw_record.amount_pkr
            internal = internal_txns.get(gw_txn_id)

            if internal is None:
                # Transaction exists in gateway but not internally — data loss risk
                items.append(ReconciliationItemResult(
                    gateway_txn_id=gw_txn_id,
                    internal_txn_id=None,
                    match_status="missing_internally",
                    gateway_amount=gw_record.amount_pkr,
                    internal_amount=None,
                    discrepancy_amount=gw_record.amount_pkr,
                ))
                discrepancies += 1
                logger.warning(
                    "Reconciliation: transaction missing internally",
                    extra={"gateway": gateway, "gateway_txn_id": gw_txn_id},
                )
            else:
                int_amount = Decimal(str(internal.amount))
                total_internal_amount += int_amount
                if gw_record.amount_pkr != int_amount:
                    items.append(ReconciliationItemResult(
                        gateway_txn_id=gw_txn_id,
                        internal_txn_id=internal.id,
                        match_status="amount_mismatch",
                        gateway_amount=gw_record.amount_pkr,
                        internal_amount=int_amount,
                        discrepancy_amount=abs(gw_record.amount_pkr - int_amount),
                    ))
                    discrepancies += 1
                else:
                    items.append(ReconciliationItemResult(
                        gateway_txn_id=gw_txn_id,
                        internal_txn_id=internal.id,
                        match_status="matched",
                        gateway_amount=gw_record.amount_pkr,
                        internal_amount=int_amount,
                        discrepancy_amount=Decimal("0.00"),
                    ))
                    matched += 1

        # Check internal transactions not in gateway (potential ghost transactions)
        for txn_id, internal in internal_txns.items():
            if txn_id not in gateway_txns:
                int_amount = Decimal(str(internal.amount))
                total_internal_amount += int_amount
                items.append(ReconciliationItemResult(
                    gateway_txn_id=txn_id,
                    internal_txn_id=internal.id,
                    match_status="missing_in_gateway",
                    gateway_amount=Decimal("0.00"),
                    internal_amount=int_amount,
                    discrepancy_amount=int_amount,
                ))
                discrepancies += 1

        now = datetime.now(timezone.utc)
        report = ReconciliationReport(
            gateway=gateway,
            settlement_date=settlement_date,
            total_records=len(gateway_txns),
            matched=matched,
            discrepancies=discrepancies,
            total_gateway_amount=total_gateway_amount,
            total_internal_amount=total_internal_amount,
            net_discrepancy=total_gateway_amount - total_internal_amount,
            items=items,
            created_at=now,
        )

        # ── 4. Persist audit JSONL ────────────────────────────────────────────
        await self._persist_audit(report)

        logger.info(
            "Reconciliation complete",
            extra={
                "gateway": gateway,
                "settlement_date": str(settlement_date),
                "matched": matched,
                "discrepancies": discrepancies,
            },
        )
        return report

    async def _persist_audit(self, report: ReconciliationReport) -> None:
        """Write reconciliation report to JSONL audit file."""
        audit_dir = Path(settings.RECONCILIATION_AUDIT_DIR)
        audit_dir.mkdir(parents=True, exist_ok=True)
        audit_file = audit_dir / f"recon_{report.gateway}_{report.settlement_date}.jsonl"
        entry = json.dumps({
            "gateway": report.gateway,
            "settlement_date": str(report.settlement_date),
            "matched": report.matched,
            "discrepancies": report.discrepancies,
            "net_discrepancy": str(report.net_discrepancy),
            "created_at": report.created_at.isoformat(),
        })
        with open(audit_file, "a") as f:
            f.write(entry + "\n")
