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


def test_factory_returns_lithic_adapter():
    """Factory must return a LithicAdapter for 'lithic' gateway."""
    from src.adapters.lithic import LithicAdapter

    mock_settings = MagicMock()
    mock_settings.LITHIC_API_KEY = "test_key"
    mock_settings.LITHIC_BASE_URL = "https://sandbox.lithic.com/v1"
    mock_settings.LITHIC_CARD_PROGRAM_TOKEN = "prog_test"
    mock_settings.FX_PKR_TO_USD_RATE = 0.0036
    mock_settings.FX_BUFFER_PCT = 2.0

    adapter = GatewayAdapterFactory.get("lithic", settings=mock_settings)
    assert isinstance(adapter, LithicAdapter)


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


def test_stripe_adapter_get_card_calls_stripe_retrieve_and_sets_api_key():
    """
    Regression test for a production bug: StripePoller calls
    ``self.stripe.get_card(issuer_card_id)`` on every polling cycle, but
    StripeIssuingAdapter had no `get_card` method at all — every call raised
    AttributeError, silently swallowed by the poller's per-card try/except,
    so the Stripe poller never detected any card cancellations in production.

    get_card must call stripe.issuing.Card.retrieve with the given id and
    set stripe.api_key first (matching every other adapter method).
    """
    adapter = StripeIssuingAdapter(secret_key="sk_test_xxx")
    fake_card = MagicMock(status="canceled")

    with patch("src.adapters.stripe_issuing.stripe") as mock_stripe:
        mock_stripe.issuing.Card.retrieve.return_value = fake_card
        result = adapter.get_card("ic_test_abc123")

    assert result is fake_card
    assert result.status == "canceled"
    mock_stripe.issuing.Card.retrieve.assert_called_once_with("ic_test_abc123")
    assert mock_stripe.api_key == "sk_test_xxx"


def test_stripe_adapter_get_card_propagates_stripe_errors():
    """
    get_card must NOT swallow Stripe API errors itself — StripePoller relies
    on catching the exception per-card so one failing card doesn't stop the
    rest of the polling sweep.
    """
    adapter = StripeIssuingAdapter(secret_key="sk_test_xxx")

    with patch("src.adapters.stripe_issuing.stripe") as mock_stripe:
        mock_stripe.issuing.Card.retrieve.side_effect = Exception("Stripe API timeout")
        with pytest.raises(Exception, match="Stripe API timeout"):
            adapter.get_card("ic_test_fail")


# ── LithicAdapter Unit Tests ──────────────────────────────────────────────────
# Lithic is the second VCN issuer (gated off by default behind
# FEATURE_LITHIC_ENABLED — see src/services/vcn.py). These mirror the
# StripeIssuingAdapter tests above since both implement the same interface.

def test_lithic_adapter_pkr_to_usd_cents_conversion():
    """Same FX formula as StripeIssuingAdapter — PKR to USD cents with buffer."""
    from src.adapters.lithic import LithicAdapter

    adapter = LithicAdapter(
        api_key="test_key",
        base_url="https://sandbox.lithic.com/v1",
        card_program_token="prog_test",
        fx_pkr_to_usd=0.0036,
        fx_buffer_pct=2.0,
    )
    cents = adapter._pkr_to_usd_cents(Decimal("1000.00"))
    assert cents == 367  # same math as the Stripe adapter test above


def test_lithic_adapter_cancel_card_calls_patch_closed():
    """cancel_card must PATCH the card with state=CLOSED and return True on success."""
    from src.adapters.lithic import LithicAdapter

    adapter = LithicAdapter(
        api_key="test_key", base_url="https://sandbox.lithic.com/v1", card_program_token="prog_test"
    )

    with patch("src.adapters.lithic.httpx") as mock_httpx:
        mock_httpx.patch.return_value = MagicMock(raise_for_status=MagicMock())
        result = adapter.cancel_card("card_tok_abc123")

    assert result is True
    mock_httpx.patch.assert_called_once()
    call_kwargs = mock_httpx.patch.call_args
    assert call_kwargs.args[0] == "https://sandbox.lithic.com/v1/cards/card_tok_abc123"
    assert call_kwargs.kwargs["json"] == {"state": "CLOSED"}


def test_lithic_adapter_cancel_card_returns_false_on_error():
    """cancel_card must return False (not raise) on Lithic API errors, matching
    StripeIssuingAdapter's contract so callers (VcnExpiryWorker) don't need
    issuer-specific error handling."""
    from src.adapters.lithic import LithicAdapter

    adapter = LithicAdapter(
        api_key="test_key", base_url="https://sandbox.lithic.com/v1", card_program_token="prog_test"
    )

    with patch("src.adapters.lithic.httpx") as mock_httpx:
        import httpx as real_httpx
        mock_httpx.HTTPError = real_httpx.HTTPError
        mock_httpx.patch.side_effect = real_httpx.HTTPError("Lithic API timeout")
        result = adapter.cancel_card("card_tok_fail")

    assert result is False


def test_lithic_adapter_create_card_sends_merchant_domain_lock():
    """create_card must include the merchant-domain-lock field when a domain
    is provided — this is the real advantage Lithic has over Stripe Issuing's
    MCC-only lock, and the reason this adapter exists at all."""
    from src.adapters.lithic import LithicAdapter

    adapter = LithicAdapter(
        api_key="test_key", base_url="https://sandbox.lithic.com/v1", card_program_token="prog_test"
    )

    fake_card = {"token": "card_tok_new", "exp_month": 12, "exp_year": 2030}
    fake_secrets = {"pan": "4111111111111111", "cvv": "123"}

    with patch("src.adapters.lithic.httpx") as mock_httpx:
        create_resp = MagicMock(raise_for_status=MagicMock())
        create_resp.json.return_value = fake_card
        secrets_resp = MagicMock(raise_for_status=MagicMock())
        secrets_resp.json.return_value = fake_secrets
        mock_httpx.post.return_value = create_resp
        mock_httpx.get.return_value = secrets_resp

        result = adapter.create_card(
            cardholder_id="ch_test",
            authorized_amount_cents=1500,
            merchant_domain="daraz.pk",
        )

    assert result["pan"] == "4111111111111111"
    assert result["issuer_card_id"] == "card_tok_new"
    post_call_kwargs = mock_httpx.post.call_args
    assert post_call_kwargs.kwargs["json"]["auth_rule_merchant_lock"] == "daraz.pk"
