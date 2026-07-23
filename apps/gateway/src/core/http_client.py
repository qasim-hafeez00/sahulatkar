import httpx
from typing import Optional
import uuid
from src.config import settings

class InternalServiceClient:
    client: Optional[httpx.AsyncClient] = None

    @classmethod
    def start(cls):
        cls.client = httpx.AsyncClient(timeout=10.0)

    @classmethod
    async def stop(cls):
        if cls.client:
            await cls.client.aclose()
            cls.client = None

    @classmethod
    def get_client(cls) -> httpx.AsyncClient:
        if not cls.client:
             raise RuntimeError("InternalServiceClient is not initialized")
        return cls.client

    @classmethod
    async def reset_for_tests(cls) -> None:
        """Best-effort explicit reset for test isolation."""
        if cls.client:
            await cls.client.aclose()
        cls.client = None

    @staticmethod
    def signed_headers(request_id: str | None = None) -> dict[str, str]:
        return {
            "X-Internal-Token": settings.INTERNAL_SERVICE_TOKEN,
            "X-Request-ID": request_id or str(uuid.uuid4()),
            "Content-Type": "application/json",
        }

    @staticmethod
    def notification_admin_headers(
        *,
        admin_id: int,
        role: str,
        permissions: list[str],
        request_id: str | None = None,
    ) -> dict[str, str]:
        """Headers for calling notification-service's admin routes (admin_notifications,
        admin_tracking). Mints a short-lived, HMAC-signed assertion (see
        sk_shared.security.create_signed_assertion) carrying the already-authenticated
        admin's role/permissions instead of forwarding plain X-Admin-Role /
        X-Admin-Permissions headers, which notification-service can no longer be
        tricked into trusting on their own.
        """
        from sk_shared.security import create_signed_assertion

        assertion = create_signed_assertion(
            {"admin_id": admin_id, "role": role, "permissions": permissions},
            secret=settings.INTERNAL_API_KEY,
            ttl_seconds=60,
        )
        return {
            "X-Admin-Assertion": assertion,
            "X-Request-ID": request_id or str(uuid.uuid4()),
            "Content-Type": "application/json",
        }
