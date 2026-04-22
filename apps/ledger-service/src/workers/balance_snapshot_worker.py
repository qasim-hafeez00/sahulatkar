from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import date, timedelta

from src.core.database import SessionLocal
from src.services.balance_service import BalanceService
from src.accounting.accounts import ACCOUNT_CODES

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run account balance snapshotting")
    parser.add_argument(
        "--as-of",
        type=lambda s: date.fromisoformat(s) if s else date.today() - timedelta(days=1),
        default=date.today() - timedelta(days=1),
        help="Date to snapshot (YYYY-MM-DD format, default: yesterday)"
    )
    return parser


async def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    async with SessionLocal() as session:
        balance_service = BalanceService(session)
        
        # Get all account codes from the mapping
        account_codes = list(ACCOUNT_CODES.values())
        
        logger.info(f"Starting balance snapshots for {len(account_codes)} accounts as of {args.as_of}")
        
        for code in account_codes:
            try:
                await balance_service.create_snapshot(code, args.as_of)
                logger.debug(f"Created snapshot for account {code}")
            except Exception:
                logger.exception(f"Failed to create snapshot for account {code}")
                
        await session.commit()
        logger.info("Balance snapshots completed")


if __name__ == "__main__":
    asyncio.run(main())
