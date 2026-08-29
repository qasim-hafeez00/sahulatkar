"""
Stripe Cardholder Service.

Every Stripe Issuing card must be attached to a Cardholder.
This service creates and caches Cardholders per user.
Cardholders are created on first VCN issuance and reused subsequently.
"""
import logging

import stripe
from sk_shared.redis_client import RedisClient

from src.config import settings

logger = logging.getLogger(__name__)


class StripeCardholderService:
    def __init__(self, redis: RedisClient):
        self._redis = redis

    async def get_or_create(self, user_id: int, user_name: str = "SahulatKar User") -> str:
        """
        Returns a Stripe Cardholder ID for the given user.
        Creates one if it doesn't exist. Uses Redis cache to avoid repeated Stripe calls.
        """
        # Cache key in Redis
        cache_key = f"sk:stripe:cardholder:{user_id}"
        cached = await self._redis.get(cache_key)
        if cached:
            if isinstance(cached, bytes):
                return cached.decode("utf-8")
            return str(cached)

        if settings.test_payment_fallbacks_enabled and (
            not settings.STRIPE_SECRET_KEY or settings.STRIPE_SECRET_KEY.startswith("mock_")
        ):
            local_id = f"ich_local_{user_id}"
            await self._redis.set(cache_key, local_id, ttl=86400 * 30)
            return local_id

        # Run blocking Stripe calls in an executor (handled upstream, but here we just block briefly)
        # For full async, we'd wrap this, but since it's cached, it only blocks once per user.
        stripe.api_key = settings.STRIPE_SECRET_KEY
        
        try:
            # Search for existing cardholder
            existing = stripe.issuing.Cardholder.list(
                metadata={"sahulatkar_user_id": str(user_id)}, 
                limit=1
            )
            if existing.data:
                cardholder_id = existing.data[0].id
            else:
                # Create new cardholder
                cardholder = stripe.issuing.Cardholder.create(
                    type="individual",
                    name=user_name,
                    billing={
                        "address": {
                            "line1": "Sahulatkar Platform",
                            "city": "Lahore",
                            "postal_code": "54000",
                            "country": "PK",
                        }
                    },
                    metadata={"sahulatkar_user_id": str(user_id)},
                )
                cardholder_id = cardholder.id
                logger.info("Stripe Cardholder created", extra={"user_id": user_id, "cardholder_id": cardholder_id})

            # Cache for 30 days
            await self._redis.set(cache_key, cardholder_id, ttl=86400 * 30)
            return cardholder_id
        except stripe.error.StripeError as exc:
            if settings.test_payment_fallbacks_enabled:
                local_id = f"ich_local_{user_id}"
                await self._redis.set(cache_key, local_id, ttl=86400 * 30)
                logger.warning(
                    "Falling back to local Stripe cardholder stub",
                    extra={"user_id": user_id, "error": str(exc)},
                )
                return local_id
            logger.error("Failed to get/create Stripe Cardholder", extra={"error": str(exc), "user_id": user_id})
            raise
