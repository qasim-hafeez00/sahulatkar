import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .constants import QueueName
from .redis_client import RedisClient


class NotificationClient:
    def __init__(self, redis: RedisClient):
        self.redis = redis

    async def push_sms(
        self,
        phone: str,
        content: str,
        template_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        """Push an SMS job to the notification queue."""
        job_id = str(uuid.uuid4())
        payload = {
            "id": job_id,
            "channel": "sms",
            "recipient": phone,
            "content": content,
            "template_id": template_id,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        
        # We push to the tail of the list (RPUSH)
        await self.redis.rpush(QueueName.NOTIFICATION_SMS, json.dumps(payload))
        return job_id

    async def push_contract_otp(self, phone: str, otp: str) -> str:
        """Helper for contract signing OTPs."""
        content = f"SahulatKar: Your contract signing code is {otp}. Valid for 3 minutes."
        return await self.push_sms(phone, content, template_id="contract_signing_otp")
