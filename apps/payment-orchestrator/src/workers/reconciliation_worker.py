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
from src.services.reconciliation import ReconciliationService

logger = logging.getLogger(__name__)


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
        PO-CRIT-02: Fetch JazzCash settlement via real SFTP using asyncssh.
        Falls back to local mock file for dev/staging environments.
        """
        logger.info(f"Fetching JazzCash settlement via SFTP for {settlement_date}")

        sftp_host = getattr(settings, "JAZZCASH_SFTP_HOST", "")
        sftp_user = getattr(settings, "JAZZCASH_SFTP_USER", "")
        sftp_password = getattr(settings, "JAZZCASH_SFTP_PASSWORD", "")
        sftp_path = getattr(settings, "JAZZCASH_SFTP_SETTLEMENT_PATH", "/settlements/")

        if sftp_host and sftp_user:
            try:
                import asyncssh
                import csv
                import io
                conn_options = asyncssh.SSHClientConnectionOptions(
                    password=sftp_password,
                    known_hosts=None,
                )
                async with asyncssh.connect(sftp_host, username=sftp_user, options=conn_options) as conn:
                    async with conn.start_sftp_client() as sftp:
                        filename = f"settlement_{settlement_date.strftime('%Y%m%d')}.csv"
                        remote_path = f"{sftp_path}{filename}"
                        content = await sftp.get(remote_path)
                        reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
                        records = []
                        for row in reader:
                            records.append(ReconciliationRecord(
                                gateway_txn_id=row["transaction_id"],
                                amount_pkr=Decimal(str(row["amount"])),
                                status=row["status"].lower(),
                                settled_at=row["settlement_date"],
                            ))
                        logger.info(f"JazzCash SFTP: fetched {len(records)} records for {settlement_date}")
                        return records
            except ImportError:
                logger.warning("asyncssh not installed \u2014 falling back to local mock file")
            except Exception as e:
                logger.error(f"JazzCash SFTP fetch failed: {e} \u2014 falling back to local mock file")

        # Dev/staging fallback: local mock file
        mock_file = Path(settings.RECONCILIATION_AUDIT_DIR) / f"mock_jazzcash_{settlement_date}.json"
        if mock_file.exists():
            with open(mock_file) as f:
                raw = json.load(f)
                return [ReconciliationRecord(**r) for r in raw]
        return []

    async def _fetch_safepay_api(self, settlement_date: date) -> list[ReconciliationRecord]:
        """
        PO-CRIT-02: Fetch SafePay settlement via real API using httpx.
        Falls back to local mock file for dev/staging environments.
        """
        logger.info(f"Fetching SafePay settlement via API for {settlement_date}")

        safepay_api_key = getattr(settings, "SAFEPAY_API_KEY", "")
        safepay_base_url = getattr(settings, "SAFEPAY_BASE_URL", "")
        safepay_secret = getattr(settings, "SAFEPAY_API_SECRET", "")

        if safepay_api_key and safepay_base_url:
            try:
                import httpx
                url = f"{safepay_base_url}/api/v1/settlements"
                headers = {
                    "X-Api-Key": safepay_api_key,
                    "X-Api-Secret": safepay_secret,
                    "Content-Type": "application/json",
                }
                params = {"date": settlement_date.isoformat()}
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(url, headers=headers, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                    records = []
                    for item in data.get("data", []):
                        records.append(ReconciliationRecord(
                            gateway_txn_id=item["transaction_id"],
                            amount_pkr=Decimal(str(item["amount"])),
                            status=item["status"].lower(),
                            settled_at=item.get("settled_at", settlement_date.isoformat()),
                        ))
                    logger.info(f"SafePay API: fetched {len(records)} records for {settlement_date}")
                    return records
            except Exception as e:
                logger.error(f"SafePay API fetch failed: {e} \u2014 falling back to local mock file")

        # Dev/staging fallback: local mock file
        mock_file = Path(settings.RECONCILIATION_AUDIT_DIR) / f"mock_safepay_{settlement_date}.json"
        if mock_file.exists():
            with open(mock_file) as f:
                raw = json.load(f)
                return [ReconciliationRecord(**r) for r in raw]
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
