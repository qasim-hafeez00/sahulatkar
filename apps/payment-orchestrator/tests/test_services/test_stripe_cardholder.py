from types import SimpleNamespace

import pytest

from src.config import settings
from src.services.stripe_cardholder import StripeCardholderService

pytestmark = pytest.mark.asyncio


async def test_cardholder_get_or_create_returns_cached(redis_mock):
    service = StripeCardholderService(redis_mock)
    await redis_mock.set("sk:stripe:cardholder:42", "ich_cached_42", ttl=60)

    result = await service.get_or_create(user_id=42)
    assert result == "ich_cached_42"


async def test_cardholder_get_or_create_local_fallback_for_mock_key(redis_mock, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "local", raising=False)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "mock_stripe", raising=False)

    service = StripeCardholderService(redis_mock)
    result = await service.get_or_create(user_id=99)

    assert result == "ich_local_99"


async def test_cardholder_get_or_create_uses_existing_stripe_cardholder(redis_mock, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production", raising=False)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_real", raising=False)

    class _ListResult:
        data = [SimpleNamespace(id="ich_existing_1")]

    monkeypatch.setattr("stripe.issuing.Cardholder.list", lambda **kwargs: _ListResult())

    service = StripeCardholderService(redis_mock)
    result = await service.get_or_create(user_id=1)

    assert result == "ich_existing_1"


async def test_cardholder_get_or_create_creates_new_when_missing(redis_mock, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production", raising=False)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_real", raising=False)

    class _EmptyListResult:
        data = []

    monkeypatch.setattr("stripe.issuing.Cardholder.list", lambda **kwargs: _EmptyListResult())
    monkeypatch.setattr(
        "stripe.issuing.Cardholder.create",
        lambda **kwargs: SimpleNamespace(id="ich_created_1"),
    )

    service = StripeCardholderService(redis_mock)
    result = await service.get_or_create(user_id=2)

    assert result == "ich_created_1"
