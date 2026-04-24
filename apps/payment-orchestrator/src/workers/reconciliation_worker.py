"""
Reconciliation Worker.

Scheduled runner that triggers gateway settlement reconciliation.
Designed to be run as a Kubernetes CronJob (daily, post-settlement).

In production this would:
  1. Download settlement file from gateway SFTP / API
  2. Parse CSV into ReconciliationRecord objects
  3. Call ReconciliationService.reconcile()
  4. Alert Slack / PagerDuty on discrepancies above threshold

For MVP: accepts a JSON settlement file from a configured directory.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from decimal import Decimal
from pathlib import Path

from sk_shared.database import SessionLocal

from src.config import settings
from src.core.logging import setup_logging
from src.schemas.reconciliation import ReconciliationImportRequest, ReconciliationRecord
from src.schemas.reconciliation import ReconciliationImportRequest, ReconciliationRecord
from src.services.reconciliation import ReconciliationService


class SettlementFetcher:
    """
    Handles fetching settlement files from gateway providers.
    Supports SFTP (JazzCash) and API-based polling (SafePay/Stripe).
    """

    async def fetch_settlement(self, gateway: str, settlement_date: date) -> list[ReconciliationRecord]:
        """
        Main entry point for fetching settlement data.
        """
        if gateway == "jazzcash":
            return await self._fetch_jazzcash_sftp(settlement_date)
        elif gateway == "safepay":
            return await self._fetch_safepay_api(settlement_date)
        
        logger.warning(f"No automated fetcher implemented for gateway: {gateway}")
        return []

    async def _fetch_jazzcash_sftp(self, settlement_date: date) -> list[ReconciliationRecord]:
        """
        Mock SFTP fetch for JazzCash settlement.
        """
        logger.info(f"Fetching JazzCash settlement via SFTP for {settlement_date}")
        # In production: use paramiko or asyncssh to download CSV from JazzCash SFTP
        return []

    async def _fetch_safepay_api(self, settlement_date: date) -> list[ReconciliationRecord]:
        """
        Mock API fetch for SafePay settlement.
        """
        logger.info(f"Fetching SafePay settlement via API for {settlement_date}")
        # In production: use httpx to call SafePay's reporting API
        return []


async def run_reconciliation(gateway: str, settlement_date: date) -> None:
    """
    Load settlement data and run reconciliation for a gateway.

    Settlement file path: {RECONCILIATION_AUDIT_DIR}/settlement_{gateway}_{date}.json
    File format: list of ReconciliationRecord JSON objects.
    """
    fetcher = SettlementFetcher()
    records = await fetcher.fetch_settlement(gateway, settlement_date)
    
    if not records:
        # Fallback to local file ingestion (GAP-08 MVP path)
        settlement_file = Path(settings.RECONCILIATION_AUDIT_DIR) / f"settlement_{gateway}_{settlement_date}.json"
        if not settlement_file.exists():
            logger.warning("Settlement file not found and fetcher returned no records", extra={"file": str(settlement_file)})
            return

        with open(settlement_file) as f:
            raw = json.load(f)

        records = [
            ReconciliationRecord(
                gateway_txn_id=r["gateway_txn_id"],
                amount_pkr=Decimal(str(r["amount_pkr"])),
                status=r["status"],
                settled_at=r["settled_at"],
            )
            for r in raw
        ]

    request = ReconciliationImportRequest(
        gateway=gateway,
        settlement_date=settlement_date,
        records=records,
    )

    async with SessionLocal() as db:
        service = ReconciliationService(db)
        report = await service.reconcile(request)

    logger.info(
        "Reconciliation complete",
        extra={
            "gateway": gateway,
            "matched": report.matched,
            "discrepancies": report.discrepancies,
            "net_discrepancy": str(report.net_discrepancy),
        },
    )

    if report.discrepancies > 0:
        logger.warning(
            "Reconciliation discrepancies found — manual review required",
            extra={
                "gateway": gateway,
                "discrepancies": report.discrepancies,
                "net_discrepancy": str(report.net_discrepancy),
            },
        )


def main() -> None:
    import argparse
    setup_logging("reconciliation-worker", settings.LOG_LEVEL)

    parser = argparse.ArgumentParser(description="Run payment reconciliation")
    parser.add_argument("--gateway", required=True, choices=["jazzcash", "safepay", "raast", "stripe"])
    parser.add_argument("--date", required=True, help="Settlement date YYYY-MM-DD")
    args = parser.parse_args()

    settlement_date = date.fromisoformat(args.date)
    asyncio.run(run_reconciliation(args.gateway, settlement_date))


if __name__ == "__main__":
    main()
