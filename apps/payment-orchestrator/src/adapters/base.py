from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Dict, Any


class PaymentAdapter(ABC):
    @abstractmethod
    async def initiate_payment(
        self, 
        order_id: int, 
        amount_pkr: Decimal, 
        callback_url: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Initiate payment with the gateway.
        Returns a dict with gateway_txn_id and optional payment_url.
        """
        pass

    @abstractmethod
    def verify_signature(self, body: bytes, signature: str) -> bool:
        """Verify the webhook signature."""
        pass

    @abstractmethod
    def parse_event(self, body: bytes) -> Dict[str, Any]:
        """Parse the webhook payload into a normalized dict."""
        pass
    @abstractmethod
    async def refund(
        self, 
        gateway_txn_id: str, 
        amount_pkr: Decimal, 
        reason: str
    ) -> Dict[str, Any]:
        """
        Initiate a refund with the gateway.
        Returns a dict with gateway_refund_id and optional status.
        """
        pass
