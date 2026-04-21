import asyncio
import logging
import time
from types import TracebackType
from typing import Optional, Type

from sk_shared.redis_client import RedisClient

logger = logging.getLogger(__name__)

class DistributedLock:
    """Redis-based distributed lock for cross-pod concurrency control.
    
    Usage:
        async with DistributedLock(redis, "lock:key", timeout=30):
            # protected logic
    """
    def __init__(
        self, 
        redis: RedisClient, 
        key: str, 
        timeout: int = 60, 
        retry_interval: float = 0.5,
        max_wait: int = 10
    ) -> None:
        self.redis = redis
        self.key = f"sk:lock:{key}"
        self.timeout = timeout
        self.retry_interval = retry_interval
        self.max_wait = max_wait
        self.lock_value = str(time.time())
        self._locked = False

    async def __aenter__(self) -> "DistributedLock":
        start_time = time.perf_counter()
        while time.perf_counter() - start_time < self.max_wait:
            if await self.redis.redis.set(self.key, self.lock_value, ex=self.timeout, nx=True):
                self._locked = True
                return self
            await asyncio.sleep(self.retry_interval)
        
        raise TimeoutError(f"Could not acquire lock for {self.key} within {self.max_wait}s")

    async def __aexit__(
        self, 
        exc_type: Optional[Type[BaseException]], 
        exc_val: Optional[BaseException], 
        exc_tb: Optional[TracebackType]
    ) -> None:
        if self._locked:
            # Lua script to safely release only if value matches (prevents accidental release of others' locks)
            lua_release = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            await self.redis.redis.eval(lua_release, 1, self.key, self.lock_value)
            self._locked = False
