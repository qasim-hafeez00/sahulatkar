from __future__ import annotations

import asyncio
import logging

from src.billing.billing_sweep import BillingSweepService
from src.config import settings
from src.core.database import SessionLocal
from sk_shared.redis_client import get_redis_client


logger = logging.getLogger(__name__)


async def main() -> None:
    redis_client = get_redis_client(settings.redis_url, db=settings.redis_db)
    async with SessionLocal() as session:
        service = BillingSweepService(session, redis=redis_client)
        result = await service.execute_sweep()
        logger.info("Billing sweep run completed", extra={"result": result})
    await redis_client.close()


if __name__ == "__main__":
    asyncio.run(main())