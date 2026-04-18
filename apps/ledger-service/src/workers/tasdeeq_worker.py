from __future__ import annotations

import asyncio
import logging

from src.core.database import SessionLocal
from src.services.tasdeeq_service import TasdeeqService


logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("Starting TASDEEQ worker", extra={"task": "tasdeeq_report"})

    async with SessionLocal() as session:
        service = TasdeeqService(session)
        result = await service.run_reporting_cycle()
        logger.info("TASDEEQ worker completed", extra=result)


if __name__ == "__main__":
    asyncio.run(main())