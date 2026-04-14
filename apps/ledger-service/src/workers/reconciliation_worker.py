from __future__ import annotations

import asyncio

from src.core.database import SessionLocal
from src.services.reconciliation_service import ReconciliationService


async def main() -> None:
    async with SessionLocal() as session:
        service = ReconciliationService(session)
        result = await service.import_snapshot(
            gateway="safepay",
            settlement_date="1970-01-01",
            expected_amount=0,
            actual_amount=0,
        )
        print(result)


if __name__ == "__main__":
    asyncio.run(main())