import logging

import httpx
from typing import Optional

from sk_shared.correlation import get_correlation_id

from src.config import settings

logger = logging.getLogger("gateway")


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
        # INF-GAP-04: default to the inbound request's correlation ID (set by
        # RequestIDMiddleware via sk_shared.correlation) instead of minting an
        # unrelated UUID, so downstream services stay traceable to the
        # original Gateway request.
        return {
            "X-Internal-Token": settings.INTERNAL_SERVICE_TOKEN,
            "X-Request-ID": request_id or get_correlation_id(),
            "Content-Type": "application/json",
        }

    @classmethod
    async def send_otp(
        cls,
        *,
        phone: str,
        otp_code: str,
        purpose: str,
        expires_in_seconds: int,
        request_id: str | None = None,
    ) -> bool:
        """Dispatch an OTP SMS via notification-service's internal endpoint.

        Every OTP flow in this service (registration, resend, password reset,
        Wakalah/Murabaha contract signing) previously wrote to
        sk_shared.notifications.NotificationClient, which enqueues onto Redis
        lists (sk:queue:notification_sms etc.) that nothing in
        notification-service ever consumed — so no OTP ever actually reached
        a real user's phone in production; only the local-dev `dev_otp`
        response field made the flow usable at all. notification-service has
        always had a working POST /internal/notifications/otp endpoint for
        exactly this — this method calls it instead.

        Best-effort: returns False (and logs) on any failure rather than
        raising, matching the pattern every other cross-service "nudge" call
        in this codebase uses (see OrderService's product-extract kickoff) —
        a transient notification-service outage must not itself block
        registration/login/contract signing, though the underlying OTP will
        then simply be undeliverable and the user must retry.
        """
        try:
            client = cls.get_client()
            resp = await client.post(
                f"{settings.NOTIFICATION_SERVICE_URL}/api/v1/internal/notifications/otp",
                json={
                    "phone": phone,
                    "otp_code": otp_code,
                    "purpose": purpose,
                    "expires_in_seconds": expires_in_seconds,
                },
                headers={
                    "X-Internal-Key": settings.INTERNAL_API_KEY,
                    "X-Request-ID": request_id or get_correlation_id(),
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.warning("OTP_SEND_FAILED purpose=%s error=%s", purpose, exc)
            return False

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
            "X-Request-ID": request_id or get_correlation_id(),
            "Content-Type": "application/json",
        }
