import httpx
from src.config import settings
from src.dispatchers.base import BaseDispatcher, DispatchResult
from src.core.middleware import provider_dispatch_errors_total

JAZZ_WHATSAPP_TEMPLATE_MAP = {
    "billing.installment_due_d1": "installment_reminder_1day",
    "billing.late_fee_applied": "late_fee_shariah_disclosure",
    "contract.murabaha_ready": "murabaha_contract_ready",
    "payment.down_payment_confirmed": "payment_confirmation",
    "delivery.confirmed": "order_delivered",
}

class JazzWhatsAppDispatcher(BaseDispatcher):
    """
    Sends WhatsApp messages via Jazz Business API.
    """

    async def send(self, *, destination: str, content: str, subject=None, notification_id: int) -> DispatchResult:
        wa_number = destination if destination.startswith("+") else f"+{destination}"

        payload = {
            "to": wa_number,
            "type": "text",
            "text": {"body": content},
        }
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(
                    settings.JAZZ_WHATSAPP_API_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {settings.JAZZ_WHATSAPP_API_KEY}",
                        "Content-Type": "application/json",
                    },
                )
            except httpx.RequestError as exc:
                provider_dispatch_errors_total.labels(
                    provider="jazz_whatsapp", 
                    error_code="REQUEST_ERROR"
                ).inc()
                return DispatchResult(
                    success=False,
                    provider_name="jazz_whatsapp",
                    failure_reason=f"JAZZ_WA_HTTP_ERROR: {str(exc)}",
                    should_retry=True,
                )

        if response.status_code in (200, 201):
            body = response.json()
            return DispatchResult(
                success=True,
                provider_message_id=str(body.get("messages", [{}])[0].get("id", "")),
                provider_name="jazz_whatsapp",
            )
        
        provider_dispatch_errors_total.labels(
            provider="jazz_whatsapp", 
            error_code=f"HTTP_{response.status_code}"
        ).inc()
        return DispatchResult(
            success=False,
            provider_name="jazz_whatsapp",
            failure_reason=f"JAZZ_WA_ERROR_{response.status_code}: {response.text[:200]}",
            should_retry=response.status_code not in (470, 400),
        )

    async def health_check(self) -> bool:
        return bool(settings.JAZZ_WHATSAPP_API_KEY)
