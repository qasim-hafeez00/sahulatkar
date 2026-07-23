from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import date

from src.billing.billing_sweep import BillingSweepService
from src.config import settings
from src.core.database import SessionLocal
from sk_shared.redis_client import get_redis_client


logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a billing sweep to detect overdue installments")
    parser.add_argument(
        "--as-of",
        type=lambda s: date.fromisoformat(s) if s else date.today(),
        default=date.today(),
        help="Date to check for overdue installments (YYYY-MM-DD format, default: today)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Number of installments to process per batch (default: 500)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (no database modifications)"
    )
    return parser


async def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    redis_client = get_redis_client(settings.redis_url, db=settings.redis_db)
    try:
        async with SessionLocal() as session:
            service = BillingSweepService(session, redis=redis_client)
            result = await service.execute_sweep(as_of=args.as_of, batch_size=args.batch_size, dry_run=args.dry_run)
            if args.dry_run:
                logger.info("Billing sweep DRY-RUN completed (no changes saved)", extra={"result": result})
            else:
                logger.info("Billing sweep run completed", extra={"result": result})
    finally:
        # Bug fix: previously `redis_client.close()` was only called on the
        # happy path, so a raised exception from execute_sweep() (or from
        # code inside the `async with SessionLocal()` block) leaked the
        # Redis connection pool for the lifetime of the process.
        await redis_client.close()


if __name__ == "__main__":
    asyncio.run(main())