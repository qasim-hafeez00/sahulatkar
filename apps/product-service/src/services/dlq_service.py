from __future__ import annotations

import json

from sk_shared.constants import QueueName
from sk_shared.redis_client import RedisClient


class DLQService:
    QUEUE_MAP = {
        "checkout": (QueueName.CHECKOUT, "sk:queue:dlq:checkout"),
        "scraping": (QueueName.SCRAPING, "sk:queue:dlq:scraping"),
    }

    def __init__(self, redis: RedisClient) -> None:
        self.redis = redis

    def _resolve_queue(self, queue: str) -> tuple[str, str]:
        try:
            return self.QUEUE_MAP[queue]
        except KeyError as exc:
            raise ValueError("INVALID_DLQ_QUEUE") from exc

    async def get_stats(self) -> dict[str, int]:
        return {
            queue_name: await self.redis.redis.llen(dlq_key)
            for queue_name, (_, dlq_key) in self.QUEUE_MAP.items()
        }

    async def list_entries(self, queue: str, limit: int = 20) -> list[dict]:
        _, dlq_key = self._resolve_queue(queue)
        raw_entries = await self.redis.redis.lrange(dlq_key, 0, max(limit - 1, 0))
        entries: list[dict] = []
        for raw in raw_entries:
            payload_raw = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            try:
                entries.append(json.loads(payload_raw))
            except Exception:
                entries.append({"raw_data": payload_raw})
        return entries

    async def reprocess(self, queue: str, entry_index: int) -> str:
        main_queue, dlq_key = self._resolve_queue(queue)
        raw_entry = await self.redis.redis.lindex(dlq_key, entry_index)
        if raw_entry is None:
            raise IndexError("DLQ_ENTRY_NOT_FOUND")

        payload_raw = raw_entry.decode("utf-8") if isinstance(raw_entry, bytes) else str(raw_entry)
        await self.redis.redis.lrem(dlq_key, 1, raw_entry)
        await self.redis.redis.lpush(main_queue, payload_raw)

        try:
            payload = json.loads(payload_raw)
        except Exception:
            return ""

        return str(payload.get("execution_id") or payload.get("job_id") or "")

    async def purge(self, queue: str) -> int:
        _, dlq_key = self._resolve_queue(queue)
        count = await self.redis.redis.llen(dlq_key)
        if count:
            await self.redis.redis.delete(dlq_key)
        return count