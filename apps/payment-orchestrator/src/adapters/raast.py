from decimal import Decimal
from typing import Dict, Any

from src.adapters.base import PaymentAdapter
from src.services.raast import RaastClient


class RaastAdapter(PaymentAdapter):
    def __init__(self, api_key: str, api_secret: str, merchant_iban: str, base_url: str = None):
        self.client = RaastClient(api_key, api_secret, merchant_iban, base_url)

    async def initiate_payment(
        self, 
        order_id: int, 
        amount_pkr: Decimal, 
        callback_url: str,
        **kwargs
    ) -> Dict[str, Any]:
        payer_iban = kwargs.get("payer_iban", "")
        result = self.client.initiate_ibft(
            order_id=order_id,
            amount_pkr=amount_pkr,
            payer_iban=payer_iban,
            callback_url=callback_url
        )
        return {
            "gateway_txn_id": result.gateway_txn_id,
            "raw_response": result.payload
        }

    def verify_signature(self, body: bytes, signature: str) -> bool:
        return self.client.verify_signature(body, signature)

    def parse_event(self, body: bytes) -> Dict[str, Any]:
        return self.client.parse_webhook(body)
    async def refund(
        self, 
        gateway_txn_id: str, 
        amount_pkr: Decimal, 
        reason: str
    ) -> Dict[str, Any]:
        result = self.client.refund(
            gateway_txn_id=gateway_txn_id,
            amount_pkr=amount_pkr,
            reason=reason
        )
        return {
            "gateway_refund_id": result["gateway_refund_id"],
            "status": result["status"],
            "message": "Refund processed"
        }
