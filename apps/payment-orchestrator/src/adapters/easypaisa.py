from decimal import Decimal
from typing import Dict, Any

from src.adapters.base import PaymentAdapter
from src.services.easypaisa import EasypaisaClient


class EasypaisaAdapter(PaymentAdapter):
    def __init__(self, store_id: str, hash_key: str, base_url: str = None):
        self.client = EasypaisaClient(store_id, hash_key, base_url)

    async def initiate_payment(
        self, 
        order_id: int, 
        amount_pkr: Decimal, 
        callback_url: str,
        **kwargs
    ) -> Dict[str, Any]:
        result = await self.client.charge(
            order_id=order_id,
            amount_pkr=amount_pkr
        )
        return {
            "gateway_txn_id": result["gateway_txn_id"],
            "success": result["success"],
            "raw_response": result["payload"]
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
        return {
            "gateway_refund_id": f"ep_ref_{gateway_txn_id}",
            "status": "success",
            "message": "Refund mock for easypaisa"
        }
