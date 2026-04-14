from __future__ import annotations

import asyncio

from src.billing.billing_sweep import BillingSweepService
from src.core.database import SessionLocal


async def main() -> None:
    async with SessionLocal() as session:
        service = BillingSweepService(session)
        result = await service.execute_sweep()
        print(result)


if __name__ == "__main__":
    asyncio.run(main())