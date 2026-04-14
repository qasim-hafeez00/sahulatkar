import time
from typing import Optional

from sk_shared.constants import RedisNS
from sk_shared.redis_client import RedisClient


async def _sliding_window_count(
    redis_client: RedisClient,
    key: str,
    window_seconds: int,
    threshold: int,
) -> tuple[bool, int]:
    now = int(time.time())
    member = f"{now}-{time.monotonic_ns()}"

    # Prefer sorted set sliding window when raw redis client is available.
    if hasattr(redis_client, "redis"):
        raw = redis_client.redis
        await raw.zadd(key, {member: now})
        await raw.zremrangebyscore(key, 0, now - window_seconds)
        count = int(await raw.zcard(key))
        await raw.expire(key, window_seconds)
        return count > threshold, count

    # Fallback for simplified/mocked clients.
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, window_seconds)
    return count > threshold, count


async def run_velocity_checks(redis_client: RedisClient, user_id: str) -> tuple[bool, Optional[str], list[str]]:
    flags: list[str] = []

    key_24h = f"{RedisNS.CREDIT_VELOCITY}:{user_id}:applications_24h"
    blocked_24h, count_24h = await _sliding_window_count(
        redis_client=redis_client,
        key=key_24h,
        window_seconds=24 * 3600,
        threshold=3,
    )
    if blocked_24h:
        return True, f"Velocity limit exceeded: {count_24h} applications in 24h", ["velocity_24h_breach"]

    key_1h = f"{RedisNS.CREDIT_VELOCITY}:{user_id}:applications_1h"
    blocked_1h, count_1h = await _sliding_window_count(
        redis_client=redis_client,
        key=key_1h,
        window_seconds=3600,
        threshold=1,
    )
    if blocked_1h:
        return True, f"Velocity limit exceeded: {count_1h} applications in 1h", ["velocity_1h_breach"]

    flags.append("velocity_clear")
    return False, None, flags
