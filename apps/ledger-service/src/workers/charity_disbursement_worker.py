from __future__ import annotations

import argparse
import asyncio
import logging

from sk_shared.redis_client import get_redis_client
from src.config import settings
from src.core.database import SessionLocal
from src.services.charity_service import CharityService


logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the periodic charity disbursement sweep (auto-disburses "
        "pending late-fee charity allocations older than the configured minimum age)."
    )
    parser.add_argument(
        "--payment-reference",
        default=None,
        help="Optional stable payment reference for this disbursement batch "
        "(default: an auto-generated timestamp-based reference).",
    )
    parser.add_argument(
        "--receipt-s3",
        default=None,
        help="Optional S3 path of the disbursement receipt to attach to the disbursed allocations.",
    )
    return parser


async def main(argv: list[str] | None = None) -> None:
    """Thin CLI wrapper around CharityService.process_charity_allocation(),
    mirroring src.workers.billing_sweep_worker's shape: acquire a Redis
    client, run one sweep against a fresh DB session, and always release the
    Redis connection pool afterward -- even if the sweep raises.

    CharityService.process_charity_allocation() already implements the full
    auto-disbursement pipeline (nisab threshold check, GL balance pre-check,
    and its own distributed Redis lock so a concurrent run -- e.g. this
    scheduled sweep racing an admin-triggered disbursement -- can't double
    post). This worker is what was actually missing: a periodic entry point
    for it, matching how billing_sweep_worker.py exposes BillingSweepService
    for cron/CronJob invocation.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    redis_client = get_redis_client(settings.redis_url, db=settings.redis_db)
    try:
        async with SessionLocal() as session:
            service = CharityService(session, redis=redis_client)
            result = await service.process_charity_allocation(
                payment_reference=args.payment_reference,
                receipt_s3=args.receipt_s3,
            )
            logger.info("Charity disbursement sweep completed", extra={"result": result})
    finally:
        # Mirrors billing_sweep_worker.main(): redis_client.close() must run
        # even when process_charity_allocation() raises, or the connection
        # pool leaks for the lifetime of the process.
        await redis_client.close()


if __name__ == "__main__":
    asyncio.run(main())
