import json
from typing import Any, Optional

import redis.asyncio as redis


class RedisClient:
    def __init__(self, red: redis.Redis) -> None:
        self.redis = red

    async def get(self, key: str) -> Optional[str]:
        val = await self.redis.get(key)
        return val.decode("utf-8") if val else None

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        await self.redis.set(name=key, value=value, ex=ttl)

    async def delete(self, key: str) -> None:
        await self.redis.delete(key)

    async def get_json(self, key: str) -> Optional[Any]:
        val = await self.get(key)
        if val:
            return json.loads(val)
        return None

    async def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        await self.set(key, json.dumps(value), ttl)

    async def publish(self, channel: str, message: str) -> None:
        await self.redis.publish(channel, message)

    async def incr(self, key: str) -> int:
        return await self.redis.incr(key)

    async def expire(self, key: str, ttl: int) -> None:
        await self.redis.expire(key, ttl)

    async def rpush(self, key: str, value: str) -> None:
        await self.redis.rpush(key, value)

    async def close(self) -> None:
        await self.redis.close()


def get_redis_client(url: str, db: int = 0) -> RedisClient:
    pool = redis.ConnectionPool.from_url(url, db=db, decode_responses=False)
    r = redis.Redis(connection_pool=pool)
    return RedisClient(r)
