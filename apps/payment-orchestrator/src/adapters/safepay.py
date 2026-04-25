from decimal import Decimal
from typing import Dict, Any

from src.adapters.base import PaymentAdapter
from src.services.safepay import SafepayClient


class SafepayAdapter(PaymentAdapter):
    def __init__(self, api_key: str, api_secret: str, base_url: str):
        self.client = SafepayClient(api_key, api_secret, base_url)

    async def initiate_payment(
        self, 
        order_id: int, 
        amount_pkr: Decimal, 
        callback_url: str,
        **kwargs
    ) -> Dict[str, Any]:
        checkout = self.client.create_checkout(
            order_id=order_id,
            amount_pkr=amount_pkr,
            callback_url=callback_url
        )
        return {
            "gateway_txn_id": checkout.gateway_txn_id,
            "payment_url": checkout.checkout_url,
            "raw_response": checkout.payload
        }

    def verify_signature(self, body: bytes, signature: str) -> bool:
        return self.client.verify_signature(body, signature)

    def parse_event(self, body: bytes) -> Dict[str, Any]:
        return self.client.parse_event(body)
    async def refund(
        self, 
        gateway_txn_id: str, 
        amount_pkr: Decimal, 
        reason: str
    ) -> Dict[str, Any]:
        result = self.client.initiate_refund(
            gateway_txn_id=gateway_txn_id,
            amount_pkr=amount_pkr,
            reason=reason
        )
        return {
            "gateway_refund_id": result.get("refund_id"),
            "status": "success" if result.get("refund_id") else "failed",
            "raw_response": result
        }
