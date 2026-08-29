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

    async def set_nx(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        """Atomic SET-if-not-exists (single Redis round trip via NX) — True if this call
        claimed the key, False if it already existed. Unlike a get-then-set pair, this closes
        the race where two concurrent callers both see "not present" and both proceed."""
        return bool(await self.redis.set(name=key, value=value, ex=ttl, nx=True))

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

    async def lpush(self, key: str, value: str) -> None:
        await self.redis.lpush(key, value)

    async def llen(self, key: str) -> int:
        return await self.redis.llen(key)

    async def lrange(self, key: str, start: int, end: int) -> list[bytes]:
        """Return a slice of the list stored at key (LRANGE start end)."""
        return await self.redis.lrange(key, start, end)

    async def lrem(self, key: str, count: int, value: str) -> int:
        """Remove elements equal to value from the list (LREM)."""
        return await self.redis.lrem(key, count, value)

    async def brpop(self, key: str, timeout: int = 0) -> Optional[tuple]:
        """Blocking pop from the right of the list (BRPOP). Returns
        (key, value) or None if timeout elapses with no item."""
        return await self.redis.brpop(key, timeout=timeout)

    async def ping(self) -> bool:
        return await self.redis.ping()

    async def close(self) -> None:
        await self.redis.close()

    # ── Redis Streams (durable, consumer-group delivery) ────────────────────
    # Unlike publish() (fire-and-forget pub/sub — a message with no subscriber
    # listening at that instant is gone forever), a stream entry persists in
    # Redis once XADD'd, and a consumer group tracks exactly which entries
    # each consumer has read-but-not-yet-acknowledged (the Pending Entries
    # List). That is what makes at-least-once delivery possible: a consumer
    # that crashes between XREADGROUP and XACK leaves its entries in the PEL,
    # where XCLAIM/XAUTOCLAIM lets another consumer (or the same one, after
    # restart) pick them back up instead of losing them.

    async def xadd(self, stream: str, fields: dict, maxlen: Optional[int] = None) -> str:
        """Durably append an entry to a Redis Stream (XADD)."""
        kwargs: dict[str, Any] = {}
        if maxlen is not None:
            kwargs["maxlen"] = maxlen
            kwargs["approximate"] = True
        msg_id = await self.redis.xadd(stream, fields, **kwargs)
        return msg_id.decode("utf-8") if isinstance(msg_id, bytes) else msg_id

    async def xgroup_create(self, stream: str, group: str, id: str = "0", mkstream: bool = True) -> None:
        """Idempotent consumer-group creation. Swallows BUSYGROUP (group
        already exists) so callers can call this unconditionally on every
        startup/poll without tracking whether it has run before."""
        try:
            await self.redis.xgroup_create(stream, group, id=id, mkstream=mkstream)
        except Exception as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def xreadgroup(
        self,
        group: str,
        consumer: str,
        streams: dict,
        count: Optional[int] = None,
        block: Optional[int] = None,
    ):
        """Read new (`>`) entries for `consumer` within `group`. Entries
        returned here are added to the group's Pending Entries List until
        xack() is called — they are NOT considered delivered until then."""
        return await self.redis.xreadgroup(group, consumer, streams=streams, count=count, block=block)

    async def xack(self, stream: str, group: str, *ids: str) -> int:
        """Acknowledge entries as fully delivered/processed, removing them
        from the group's Pending Entries List."""
        return await self.redis.xack(stream, group, *ids)

    async def xautoclaim(
        self,
        stream: str,
        group: str,
        consumer: str,
        min_idle_time: int,
        start_id: str = "0-0",
        count: Optional[int] = None,
    ):
        """Reassign PEL entries that have sat unacknowledged for at least
        `min_idle_time` ms (i.e. their original consumer crashed or hung
        between XREADGROUP and XACK) to `consumer`, so they get retried
        instead of silently lost. Returns (next_start_id, claimed_entries,
        deleted_ids)."""
        return await self.redis.xautoclaim(
            stream, group, consumer, min_idle_time, start_id=start_id, count=count
        )


def get_redis_client(url: str, db: int = 0) -> RedisClient:
    pool = redis.ConnectionPool.from_url(url, db=db, decode_responses=False)
    r = redis.Redis(connection_pool=pool)
    return RedisClient(r)
