from __future__ import annotations

import asyncio

from src.config import settings
from sk_shared.redis_client import RedisClient

class VcnVerifier:
    def __init__(self, redis: RedisClient) -> None:
        self.redis = redis

    async def verify_charge(self, vcn_id: int, timeout_seconds: int | None = None) -> bool:
        """Poll Redis for Stripe charge confirmation from webhooks.
        
        Updated to use exponential backoff with jitter to reduce Redis load
        during peak surges while maintaining responsiveness.
        """
        import random
        import time
        
        confirmed_key = f"sk:vcn:charge:confirmed:{vcn_id}"
        legacy_key = f"sk:vcn:pending_verification:{vcn_id}"
        
        timeout = timeout_seconds or settings.VCN_VERIFICATION_TIMEOUT_SECONDS
        start_time = time.perf_counter()
        
        # Initial wait of 0.5s, doubling up to 10s.
        wait_time = 0.5
        
        while (time.perf_counter() - start_time) < timeout:
            # 1. Check for modern confirmation key
            if await self.redis.get(confirmed_key):
                await self.redis.delete(confirmed_key)
                return True
            
            # 2. Check for legacy confirmation signal
            if await self.redis.get(legacy_key) == "confirmed":
                await self.redis.delete(legacy_key)
                return True
            
            # Calculate next wait with jitter
            jitter = random.uniform(0.8, 1.2)
            actual_wait = min(wait_time * jitter, timeout - (time.perf_counter() - start_time))
            
            if actual_wait <= 0:
                break
                
            await asyncio.sleep(actual_wait)
            wait_time = min(wait_time * 2, 10.0) # Cap at 10s
            
        return False
