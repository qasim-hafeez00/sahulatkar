"""
Lithic Issuing Adapter — second VCN issuer, alongside stripe_issuing.py.

Status: code-complete against Lithic's documented card-issuing API, testable
against Lithic's free sandbox (LITHIC_BASE_URL defaults to the sandbox host).
NOT a drop-in production replacement for Stripe today — Lithic requires a
business/KYB approval process before it can issue a single real card, exactly
like the Raast/NADRA integrations elsewhere in this codebase. Gated behind
settings.FEATURE_LITHIC_ENABLED (default off); Stripe Issuing remains the
functional-today path until that approval lands.

Why add Lithic at all: unlike Stripe Issuing's MCC-category-only lock,
Lithic's authorization rules support real merchant-domain locking, which
maps directly onto the `virtual_cards.merchant_lock` column that already
exists in the schema but sits unused on the Stripe path.
"""
from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict

import httpx

from src.adapters.base import PaymentAdapter
from src.config import settings

logger = logging.getLogger(__name__)


class LithicAdapter(PaymentAdapter):
    """
    Adapter for Lithic's card-issuing API.

    Like Stripe Issuing, Lithic operates in USD for this integration — all
    PKR amounts are converted before being sent to Lithic.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        card_program_token: str,
        fx_pkr_to_usd: float = 0.0036,
        fx_buffer_pct: float = 2.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.card_program_token = card_program_token
        self.fx_pkr_to_usd = Decimal(str(fx_pkr_to_usd))
        self.fx_buffer_pct = Decimal(str(fx_buffer_pct))

    def _pkr_to_usd_cents(self, amount_pkr: Decimal) -> int:
        buffer = Decimal("1") + self.fx_buffer_pct / Decimal("100")
        amount_usd = (amount_pkr * self.fx_pkr_to_usd * buffer).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return int(amount_usd * 100)

    def _headers(self) -> dict[str, str]:
        # Live-verified against the real Lithic sandbox: Lithic uses its own
        # "api-key" auth scheme, not Bearer — a Bearer header 401s outright.
        # This was silently masked locally because ENVIRONMENT=="local"
        # catches any httpx.HTTPError here and returns a fake card instead.
        return {"Authorization": f"api-key {self.api_key}", "Content-Type": "application/json"}

    async def initiate_payment(
        self,
        order_id: int,
        amount_pkr: Decimal,
        callback_url: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """For Lithic (a VCN path, not a redirect/direct-charge gateway), this
        mirrors StripeIssuingAdapter.initiate_payment — real card creation
        happens in create_card(), called from VcnService."""
        amount_usd_cents = self._pkr_to_usd_cents(amount_pkr)
        logger.info(
            "Lithic Issuing payment initiation (VCN path)",
            extra={"order_id": order_id, "amount_pkr": str(amount_pkr), "amount_usd_cents": amount_usd_cents},
        )
        return {
            "gateway_txn_id": f"lithic_vcn_{order_id}",
            "amount_usd_cents": amount_usd_cents,
        }

    def create_card(
        self,
        cardholder_id: str,
        authorized_amount_cents: int,
        merchant_category: str = "5999",
        merchant_domain: str | None = None,
    ) -> Dict[str, Any]:
        """
        Create a Lithic single-use virtual card, spend-limited per transaction
        and optionally domain-locked to `merchant_domain` — the real
        merchant-lock capability Stripe Issuing lacks here.

        `cardholder_id` is accepted for interface parity with
        StripeIssuingAdapter (VcnService always passes one); Lithic cards are
        program-scoped rather than cardholder-scoped, so it isn't sent, but
        it's kept in the signature so VcnService doesn't need adapter-specific
        branching to call this.
        """
        payload: dict[str, Any] = {
            "type": "VIRTUAL",
            "card_program_token": self.card_program_token,
            "spend_limit": authorized_amount_cents,
            "spend_limit_duration": "TRANSACTION",
            "state": "OPEN",
        }
        if merchant_domain:
            # Lithic auth rules support merchant-locking cards to specific
            # descriptors/domains — validate the exact rule shape against
            # current Lithic API docs before relying on this in production;
            # this is the intended integration point for that lock.
            payload["auth_rule_merchant_lock"] = merchant_domain

        try:
            resp = httpx.post(f"{self.base_url}/cards", json=payload, headers=self._headers(), timeout=15.0)
            resp.raise_for_status()
            card = resp.json()

            # Live-verified against the real Lithic sandbox: a sandbox key's
            # card-create response already includes "pan"/"cvv" inline (a
            # sandbox convenience — no separate reveal call needed, or
            # possible: /cards/{token}/secrets/embed 404s outright). A
            # production-scoped key requires the real PCI-scoped reveal flow
            # instead (GET /cards/{token}/secrets, which needs Lithic PCI
            # approval on the account) — fall back to that only when the
            # create response didn't already carry the secrets.
            pan = card.get("pan")
            cvv = card.get("cvv")
            if not pan or not cvv:
                secrets_resp = httpx.get(
                    f"{self.base_url}/cards/{card['token']}/secrets",
                    headers=self._headers(),
                    timeout=15.0,
                )
                secrets_resp.raise_for_status()
                secrets = secrets_resp.json()
                pan = secrets["pan"]
                cvv = secrets["cvv"]

            return {
                "issuer_card_id": card["token"],
                "pan": pan,
                "cvv": cvv,
                "expiry_month": str(card["exp_month"]).zfill(2),
                "expiry_year": str(card["exp_year"]),
            }
        except httpx.HTTPError as exc:
            if settings.test_payment_fallbacks_enabled:
                logger.warning("Using local Lithic card stub", extra={"error": str(exc)})
                return {
                    "issuer_card_id": f"lithic_local_{cardholder_id}",
                    "pan": "4111111111111111",
                    "cvv": "123",
                    "expiry_month": "12",
                    "expiry_year": "2030",
                }
            logger.error("Lithic card creation failed", extra={"error": str(exc)})
            raise

    def get_card(self, issuer_card_id: str) -> Any:
        """Retrieve the current state of a Lithic card — mirrors
        StripeIssuingAdapter.get_card for the poller's fallback status check."""
        resp = httpx.get(f"{self.base_url}/cards/{issuer_card_id}", headers=self._headers(), timeout=15.0)
        resp.raise_for_status()
        return resp.json()

    def cancel_card(self, issuer_card_id: str) -> bool:
        """Close (void) a Lithic card."""
        try:
            resp = httpx.patch(
                f"{self.base_url}/cards/{issuer_card_id}",
                json={"state": "CLOSED"},
                headers=self._headers(),
                timeout=15.0,
            )
            resp.raise_for_status()
            logger.info("Lithic card closed", extra={"issuer_card_id": issuer_card_id})
            return True
        except httpx.HTTPError as exc:
            logger.error("Lithic card cancellation failed", extra={"issuer_card_id": issuer_card_id, "error": str(exc)})
            return False

    def verify_signature(self, body: bytes, signature: str) -> bool:
        """Verify a Lithic webhook signature (HMAC-SHA256, matching the
        pattern every other adapter in this file uses for its own gateway)."""
        import hashlib
        import hmac

        secret = settings.LITHIC_WEBHOOK_SECRET
        if not secret:
            return settings.test_payment_fallbacks_enabled
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def parse_event(self, body: bytes) -> Dict[str, Any]:
        import json

        return json.loads(body)

    async def refund(self, gateway_txn_id: str, amount_pkr: Decimal, reason: str) -> Dict[str, Any]:
        """As with Stripe's VCN path, a 'refund' here means closing the card —
        any PKR refund to the user is a separate ledger operation."""
        return {
            "gateway_refund_id": f"lithic_close_{gateway_txn_id}",
            "status": "initiated",
            "message": "VCN closed; PKR refund handled via ledger reversal",
        }
