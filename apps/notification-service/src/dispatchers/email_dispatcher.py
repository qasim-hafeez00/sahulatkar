import httpx
from src.config import settings
from src.dispatchers.base import BaseDispatcher, DispatchResult
from src.core.middleware import provider_dispatch_errors_total


class SendGridEmailDispatcher(BaseDispatcher):
    """
    SendGrid transactional email.
    """

    async def send(self, *, destination: str, content: str, subject=None, notification_id: int) -> DispatchResult:
        payload = {
            "personalizations": [
                {
                    "to": [{"email": destination}],
                    "subject": subject or "Notification from SahulatKar",
                }
            ],
            "from": {
                "email": settings.SENDGRID_FROM_EMAIL,
                "name": settings.SENDGRID_FROM_NAME,
            },
            "content": [
                {"type": "text/plain", "value": content}
            ],
            # Custom arg for delivery receipt correlation
            "custom_args": {
                "notification_id": str(notification_id),
            },
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
                        "Content-Type": "application/json",
                    },
                )
            except httpx.RequestError as exc:
                provider_dispatch_errors_total.labels(
                    provider="sendgrid", 
                    error_code="REQUEST_ERROR"
                ).inc()
                return DispatchResult(
                    success=False,
                    provider_name="sendgrid",
                    failure_reason=f"SENDGRID_HTTP_ERROR: {str(exc)}",
                    should_retry=True,
                )

        if response.status_code == 202:
            message_id = response.headers.get("X-Message-Id", "")
            return DispatchResult(
                success=True,
                provider_message_id=message_id,
                provider_name="sendgrid",
            )

        provider_dispatch_errors_total.labels(
            provider="sendgrid", 
            error_code=f"HTTP_{response.status_code}"
        ).inc()
        return DispatchResult(
            success=False,
            provider_name="sendgrid",
            failure_reason=f"SENDGRID_ERROR_{response.status_code}: {response.text[:200]}",
            should_retry=response.status_code >= 500,
        )

    async def health_check(self) -> bool:
        return bool(settings.SENDGRID_API_KEY)
