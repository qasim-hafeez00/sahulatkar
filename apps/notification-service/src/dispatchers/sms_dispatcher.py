import httpx
from typing import Optional
from src.config import settings
from src.dispatchers.base import BaseDispatcher, DispatchResult
from src.core.middleware import provider_dispatch_errors_total

# OTP SMS Template — NEVER include OTP in logs
OTP_TEMPLATE = "Your SahulatKar OTP is {otp}. Valid for {expires_min} minutes. Do not share this code."

# Character limit for a single SMS segment (GSM-7 encoding)
SMS_MAX_CHARS = 160


class TwilioSMSDispatcher(BaseDispatcher):
    """Fallback SMS via Twilio REST API."""

    def __init__(self):
        pass

    async def send(self, *, destination: str, content: str, subject=None, notification_id: int) -> DispatchResult:
        url = f"/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json"
        async with httpx.AsyncClient(
            base_url="https://api.twilio.com",
            auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
            timeout=15.0,
        ) as client:
            response = await client.post(url, data={
                "To": destination,
                "From": settings.TWILIO_SMS_FROM,
                "Body": content,
            })
        if response.status_code == 201:
            sid = response.json().get("sid", "")
            return DispatchResult(success=True, provider_message_id=sid, provider_name="twilio_sms")
        
        provider_dispatch_errors_total.labels(
            provider="twilio_sms", 
            error_code=f"HTTP_{response.status_code}"
        ).inc()
        
        return DispatchResult(
            success=False,
            failure_reason=f"TWILIO_ERROR_{response.status_code}",
            provider_name="twilio_sms",
        )

    async def health_check(self) -> bool:
        return bool(settings.TWILIO_AUTH_TOKEN)


class JazzSMSDispatcher(BaseDispatcher):
    """
    Primary SMS dispatcher via Jazz SMS API (Pakistani carrier).
    Automatic failover to Twilio on connection error or 5xx response.
    """

    def __init__(self):
        self._fallback: Optional[TwilioSMSDispatcher] = None
        if settings.SMS_FALLBACK_PROVIDER == "twilio" and settings.TWILIO_AUTH_TOKEN:
            self._fallback = TwilioSMSDispatcher()

    async def send(self, *, destination: str, content: str, subject=None, notification_id: int) -> DispatchResult:
        # Enforce single-segment for critical messages
        if len(content) > SMS_MAX_CHARS:
            content = content[:SMS_MAX_CHARS - 3] + "..."

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    settings.JAZZ_SMS_API_URL,
                    json={
                        "username": settings.JAZZ_SMS_USERNAME,
                        "password": settings.JAZZ_SMS_PASSWORD,
                        "to": destination,
                        "from": settings.JAZZ_SMS_SENDER_ID,
                        "message": content,
                        "flash": 0,
                    },
                    headers={"Content-Type": "application/json"},
                )
            
            if response.status_code == 200:
                body = response.json()
                return DispatchResult(
                    success=True,
                    provider_message_id=str(body.get("message_id", "")),
                    provider_name="jazz_sms",
                )
            
            provider_dispatch_errors_total.labels(
                provider="jazz_sms", 
                error_code=f"HTTP_{response.status_code}"
            ).inc()
            
            if response.status_code in (400, 422):
                # Permanent failure — invalid number, do not retry
                return DispatchResult(
                    success=False,
                    provider_name="jazz_sms",
                    failure_reason=f"JAZZ_PERMANENT_FAILURE: {response.text}",
                    should_retry=False,
                )
            
            # 5xx or other — attempt fallback
            if self._fallback:
                return await self._fallback.send(
                    destination=destination, content=content,
                    subject=subject, notification_id=notification_id,
                )
            
            return DispatchResult(
                success=False,
                provider_name="jazz_sms",
                failure_reason=f"JAZZ_API_ERROR_{response.status_code}",
            )

        except httpx.ConnectError:
            provider_dispatch_errors_total.labels(
                provider="jazz_sms", 
                error_code="CONNECTION_ERROR"
            ).inc()
            if self._fallback:
                return await self._fallback.send(
                    destination=destination, content=content,
                    subject=subject, notification_id=notification_id,
                )
            return DispatchResult(success=False, failure_reason="JAZZ_UNREACHABLE", provider_name="jazz_sms")

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(settings.JAZZ_SMS_API_URL + "/health")
                return response.status_code < 500
        except Exception:
            return False
