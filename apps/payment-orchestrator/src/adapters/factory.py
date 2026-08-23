"""
GatewayAdapterFactory — selects the correct adapter at runtime.

All gateway calls go through this factory, ensuring the adapter layer
is always used and direct client instantiation is not scattered through
business logic.
"""
from __future__ import annotations

from src.adapters.base import PaymentAdapter


class GatewayAdapterFactory:
    @staticmethod
    def get(gateway: str, settings=None) -> PaymentAdapter:
        """
        Return the PaymentAdapter for the given gateway name.

        Args:
            gateway: One of 'safepay', 'jazzcash', 'raast', 'stripe'.
            settings: Settings object; if None, imports from src.config.

        Raises:
            ValueError: If the gateway name is not recognized.
        """
        if settings is None:
            from src.config import settings as _settings
            settings = _settings

        if gateway == "safepay":
            from src.adapters.safepay import SafepayAdapter
            return SafepayAdapter(
                api_key=settings.SAFEPAY_API_KEY,
                api_secret=settings.SAFEPAY_API_SECRET,
                base_url=settings.SAFEPAY_BASE_URL,
                webhook_secret=settings.SAFEPAY_WEBHOOK_SECRET,
            )

        if gateway == "jazzcash":
            from src.adapters.jazzcash import JazzCashAdapter
            return JazzCashAdapter(
                merchant_id=settings.JAZZCASH_MERCHANT_ID,
                password=settings.JAZZCASH_PASSWORD,
                base_url=settings.JAZZCASH_BASE_URL,
            )

        if gateway == "raast":
            from src.adapters.raast import RaastAdapter
            return RaastAdapter(
                api_key=settings.RAAST_API_KEY,
                api_secret=settings.RAAST_API_SECRET,
                merchant_iban=settings.RAAST_MERCHANT_IBAN,
                base_url=settings.RAAST_BASE_URL,
            )

        if gateway == "stripe":
            from src.adapters.stripe_issuing import StripeIssuingAdapter
            return StripeIssuingAdapter(
                secret_key=settings.STRIPE_SECRET_KEY,
                fx_pkr_to_usd=settings.FX_PKR_TO_USD_RATE,
                fx_buffer_pct=settings.FX_BUFFER_PCT,
            )

        if gateway == "lithic":
            from src.adapters.lithic import LithicAdapter
            return LithicAdapter(
                api_key=settings.LITHIC_API_KEY,
                base_url=settings.LITHIC_BASE_URL,
                card_program_token=settings.LITHIC_CARD_PROGRAM_TOKEN,
                fx_pkr_to_usd=settings.FX_PKR_TO_USD_RATE,
                fx_buffer_pct=settings.FX_BUFFER_PCT,
            )

        if gateway == "easypaisa":
            from src.adapters.easypaisa import EasypaisaAdapter
            return EasypaisaAdapter(
                store_id=settings.EASYPAISA_STORE_ID,
                hash_key=settings.EASYPAISA_HASH_KEY,
                base_url=settings.EASYPAISA_BASE_URL,
            )

        raise ValueError(f"Unknown gateway: '{gateway}'. Expected one of: safepay, jazzcash, raast, stripe, lithic, easypaisa.")
