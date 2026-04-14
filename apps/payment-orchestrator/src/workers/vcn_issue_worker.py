from __future__ import annotations

import asyncio
import json

from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import QueueName
from sk_shared.redis_client import RedisClient

from src.services.vcn import VcnService


class VcnIssueWorker:
    def __init__(self, db: AsyncSession, redis: RedisClient, concurrency: int = 1) -> None:
        self.db = db
        self.redis = redis
        self.concurrency = concurrency
        self.running = True

    async def run(self) -> None:
        while self.running:
            job = await self.redis.redis.brpop(QueueName.VCN_ISSUE, timeout=5)
            if job is None:
                await asyncio.sleep(0)
                continue

            payload = json.loads(job[1].decode("utf-8"))
            service = VcnService(self.db, self.redis)
            await service.issue_vcn(
                order_id=payload["order_id"],
                amount_pkr=payload["amount_pkr"],
                merchant_domain=payload.get("merchant_domain"),
            )