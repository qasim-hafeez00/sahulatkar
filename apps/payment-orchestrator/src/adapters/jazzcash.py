from decimal import Decimal
from typing import Dict, Any

from src.adapters.base import PaymentAdapter
from src.services.jazzcash import JazzCashClient


class JazzCashAdapter(PaymentAdapter):
    def __init__(self, merchant_id: str, password: str, base_url: str = None):
        self.client = JazzCashClient(merchant_id, password, base_url)

    async def initiate_payment(
        self, 
        order_id: int, 
        amount_pkr: Decimal, 
        callback_url: str,
        **kwargs
    ) -> Dict[str, Any]:
        result = self.client.charge(
            order_id=order_id,
            amount_pkr=amount_pkr
        )
        return {
            "gateway_txn_id": result.gateway_txn_id,
            "success": result.success,
            "raw_response": result.payload
        }

    def verify_signature(self, body: bytes, signature: str) -> bool:
        return self.client.verify_signature(body, signature)

    def parse_event(self, body: bytes) -> Dict[str, Any]:
        return self.client.parse_event(body)
