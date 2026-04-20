from __future__ import annotations

import asyncio
from typing import Optional

from sk_shared.redis_client import RedisClient

class VcnVerifier:
    def __init__(self, redis: RedisClient) -> None:
        self.redis = redis

    async def verify_charge(self, vcn_id: int, timeout_seconds: int = 20) -> bool:
        """Poll Redis for Stripe charge confirmation from webhooks.
        
        Addresses GAP-21 and the 'blocking threads' issue by having a dedicated 
        verification loop that can be easily updated to a more reactive pattern 
        later (e.g. Pub/Sub).
        """
        confirmed_key = f"sk:vcn:charge:confirmed:{vcn_id}"
        legacy_key = f"sk:vcn:pending_verification:{vcn_id}"
        
        # We poll every 2 seconds for a total of timeout_seconds.
        # This keeps a worker slot active but ensures we pick up the webhook 
        # as soon as it arrives.
        max_attempts = max(1, timeout_seconds // 2)
        
        for _ in range(max_attempts):
            # 1. Check for modern confirmation key
            if await self.redis.get(confirmed_key):
                await self.redis.delete(confirmed_key)
                return True
            
            # 2. Check for legacy confirmation signal
            if await self.redis.get(legacy_key) == "confirmed":
                await self.redis.delete(legacy_key)
                return True
            
            await asyncio.sleep(2)
            
        return False
