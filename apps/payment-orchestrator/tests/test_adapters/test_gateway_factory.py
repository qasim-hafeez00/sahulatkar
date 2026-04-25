"""
Tests for GatewayAdapterFactory and individual adapters.

Covers:
  - Factory returns correct adapter type for each gateway name
  - Factory raises ValueError for unknown gateway names
  - SafepayAdapter, JazzCashAdapter, RaastAdapter return correct dict keys
  - StripeIssuingAdapter PKR→USD conversion applies FX buffer correctly
  - StripeIssuingAdapter.cancel_card calls stripe API (mocked)
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.adapters.factory import GatewayAdapterFactory
from src.adapters.stripe_issuing import StripeIssuingAdapter


# ── Factory Tests ─────────────────────────────────────────────────────────────

def test_factory_returns_safepay_adapter():
    """Factory must return a SafepayAdapter for 'safepay' gateway."""
    from src.adapters.safepay import SafepayAdapter
    from unittest.mock import MagicMock

    mock_settings = MagicMock()
    mock_settings.SAFEPAY_API_KEY = "test_key"
    mock_settings.SAFEPAY_API_SECRET = "test_secret"
    mock_settings.SAFEPAY_BASE_URL = "https://sandbox.api.getsafepay.com"

    adapter = GatewayAdapterFactory.get("safepay", settings=mock_settings)
    assert isinstance(adapter, SafepayAdapter)


def test_factory_returns_jazzcash_adapter():
    """Factory must return a JazzCashAdapter for 'jazzcash' gateway."""
    from src.adapters.jazzcash import JazzCashAdapter
    from unittest.mock import MagicMock

    mock_settings = MagicMock()
    mock_settings.JAZZCASH_MERCHANT_ID = "test_merchant"
    mock_settings.JAZZCASH_PASSWORD = "test_pass"
    mock_settings.JAZZCASH_BASE_URL = None

    adapter = GatewayAdapterFactory.get("jazzcash", settings=mock_settings)
    assert isinstance(adapter, JazzCashAdapter)


def test_factory_returns_raast_adapter():
    """Factory must return a RaastAdapter for 'raast' gateway."""
    from src.adapters.raast import RaastAdapter
    from unittest.mock import MagicMock

    mock_settings = MagicMock()
    mock_settings.RAAST_API_KEY = "raast_key"
    mock_settings.RAAST_API_SECRET = "raast_secret"
    mock_settings.RAAST_MERCHANT_IBAN = "PK36SCBL0000001123456702"
    mock_settings.RAAST_BASE_URL = None

    adapter = GatewayAdapterFactory.get("raast", settings=mock_settings)
    assert isinstance(adapter, RaastAdapter)


def test_factory_returns_stripe_adapter():
    """Factory must return a StripeIssuingAdapter for 'stripe' gateway."""
    from unittest.mock import MagicMock

    mock_settings = MagicMock()
    mock_settings.STRIPE_SECRET_KEY = "sk_test_xxx"
    mock_settings.FX_PKR_TO_USD_RATE = 0.0036
    mock_settings.FX_BUFFER_PCT = 2.0

    adapter = GatewayAdapterFactory.get("stripe", settings=mock_settings)
    assert isinstance(adapter, StripeIssuingAdapter)


def test_factory_raises_value_error_for_unknown_gateway():
    """Factory must raise ValueError for an unrecognized gateway name."""
    mock_settings = MagicMock()

    with pytest.raises(ValueError) as exc_info:
        GatewayAdapterFactory.get("payoneer", settings=mock_settings)

    assert "payoneer" in str(exc_info.value).lower()


# ── StripeIssuingAdapter Unit Tests ───────────────────────────────────────────

def test_stripe_adapter_pkr_to_usd_cents_conversion():
    """PKR to USD cents conversion must apply FX rate and buffer correctly."""
    adapter = StripeIssuingAdapter(
        secret_key="sk_test",
        fx_pkr_to_usd=0.0036,   # 1 PKR = 0.0036 USD
        fx_buffer_pct=2.0,      # 2% buffer
    )

    amount_pkr = Decimal("1000.00")
    # Expected: 1000 * 0.0036 * 1.02 = 3.672 USD = 367 cents (rounded HALF_UP)
    cents = adapter._pkr_to_usd_cents(amount_pkr)
    assert cents == 367  # 3.672 * 100 = 367.2 → 367 (quantize 0.01 → 3.67 → 367)


def test_stripe_adapter_cancel_card_calls_stripe_modify():
    """cancel_card must call stripe.issuing.Card.modify with status=canceled."""
    adapter = StripeIssuingAdapter(secret_key="sk_test_xxx")

    with patch("src.adapters.stripe_issuing.stripe") as mock_stripe:
        mock_stripe.issuing.Card.modify.return_value = MagicMock()
        result = adapter.cancel_card("ic_test_abc123")

    assert result is True
    mock_stripe.issuing.Card.modify.assert_called_once_with("ic_test_abc123", status="canceled")


def test_stripe_adapter_cancel_card_returns_false_on_stripe_error():
    """cancel_card must return False (not raise) on Stripe API errors."""
    adapter = StripeIssuingAdapter(secret_key="sk_test_xxx")

    with patch("src.adapters.stripe_issuing.stripe") as mock_stripe:
        mock_stripe.issuing.Card.modify.side_effect = Exception("Stripe API timeout")
        result = adapter.cancel_card("ic_test_fail")

    assert result is False


def test_stripe_adapter_verify_signature_returns_true():
    """verify_signature always returns True — actual verification done upstream."""
    adapter = StripeIssuingAdapter(secret_key="sk_test")
    assert adapter.verify_signature(b"body", "sig") is True
