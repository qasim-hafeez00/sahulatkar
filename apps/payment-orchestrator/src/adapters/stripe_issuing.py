"""
Stripe Issuing Adapter.

Wraps Stripe Issuing API for VCN card operations:
  - Virtual card creation
  - Card cancellation (void)
  - PKR → USD conversion for authorized amounts
"""
from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict

import stripe

from src.adapters.base import PaymentAdapter

logger = logging.getLogger(__name__)


class StripeIssuingAdapter(PaymentAdapter):
    """
    Adapter for Stripe Issuing API.

    Stripe operates in the card's native currency (USD for international issuers).
    All PKR amounts are converted to USD before being sent to Stripe.
    """

    def __init__(
        self,
        secret_key: str,
        fx_pkr_to_usd: float = 0.0036,
        fx_buffer_pct: float = 2.0,
    ) -> None:
        self.secret_key = secret_key
        self.fx_pkr_to_usd = Decimal(str(fx_pkr_to_usd))
        self.fx_buffer_pct = Decimal(str(fx_buffer_pct))

    def _pkr_to_usd_cents(self, amount_pkr: Decimal) -> int:
        """
        Convert PKR to USD cents for Stripe.
        Applies a FX buffer to protect against rate drift.
        """
        buffer = Decimal("1") + self.fx_buffer_pct / Decimal("100")
        amount_usd = (amount_pkr * self.fx_pkr_to_usd * buffer).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return int(amount_usd * 100)  # Stripe expects cents

    async def initiate_payment(
        self,
        order_id: int,
        amount_pkr: Decimal,
        callback_url: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        For Stripe Issuing, 'initiate_payment' creates a virtual card.
        Returns a stub for compatibility — real card creation is in VcnService.
        """
        amount_usd_cents = self._pkr_to_usd_cents(amount_pkr)
        logger.info(
            "Stripe Issuing payment initiation (VCN path)",
            extra={"order_id": order_id, "amount_pkr": str(amount_pkr), "amount_usd_cents": amount_usd_cents},
        )
        return {
            "gateway_txn_id": f"stripe_vcn_{order_id}",
            "amount_usd_cents": amount_usd_cents,
        }

    def cancel_card(self, issuer_card_id: str) -> bool:
        """
        Cancel (void) a Stripe Issuing card.
        Calls stripe.issuing.Card.modify(id, status="canceled").

        Returns True if canceled successfully, False on error.
        """
        try:
            stripe.api_key = self.secret_key
            stripe.issuing.Card.modify(issuer_card_id, status="canceled")
            logger.info("Stripe card canceled", extra={"issuer_card_id": issuer_card_id})
            return True
        except Exception as exc:
            logger.error(
                "Stripe card cancellation failed",
                extra={"issuer_card_id": issuer_card_id, "error": str(exc)},
            )
            return False

    def verify_signature(self, body: bytes, signature: str) -> bool:
        """Stripe signature verification is handled in the webhook endpoint via stripe.Webhook."""
        return True  # Handled upstream by stripe.Webhook.construct_event

    def parse_event(self, body: bytes) -> Dict[str, Any]:
        """Parse Stripe event — handled upstream in the webhook endpoint."""
        import json
        return json.loads(body)
    async def refund(
        self, 
        gateway_txn_id: str, 
        amount_pkr: Decimal, 
        reason: str
    ) -> Dict[str, Any]:
        """
        Refund for Stripe Issuing (VCN) path.
        For VCNs, we usually void the card. A PKR refund to the user
        is a separate ledger operation.
        """
        return {
            "gateway_refund_id": f"stripe_void_{gateway_txn_id}",
            "status": "initiated",
            "message": "VCN voided; PKR refund handled via ledger reversal"
        }
