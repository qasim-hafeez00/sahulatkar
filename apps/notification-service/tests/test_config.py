"""
Tests for Settings runtime validation (src/config.py).

Covers:
  - INTERNAL_API_KEY must be changed outside local (pre-existing check)
  - P1-08: webhook secrets (AfterShip/SendGrid/SMS/WhatsApp) must all be set
    outside local — each secures a webhook handler that otherwise silently
    accepts unsigned/forged requests instead of rejecting them.
"""
import pytest

from src.config import Settings


def _real_secrets() -> dict:
    return {
        "INTERNAL_API_KEY": "a-real-production-key",
        "AFTERSHIP_WEBHOOK_SECRET": "real-aftership-secret",
        "SENDGRID_WEBHOOK_SECRET": "real-sendgrid-public-key",
        "JAZZ_SMS_WEBHOOK_SECRET": "real-jazz-sms-secret",
        "JAZZ_WHATSAPP_WEBHOOK_SECRET": "real-jazz-whatsapp-secret",
    }


def test_local_environment_boots_with_all_webhook_secrets_blank():
    Settings(ENVIRONMENT="local")


def test_production_boots_cleanly_with_all_real_secrets():
    Settings(ENVIRONMENT="production", **_real_secrets())


@pytest.mark.parametrize(
    "missing_field",
    [
        "AFTERSHIP_WEBHOOK_SECRET",
        "SENDGRID_WEBHOOK_SECRET",
        "JAZZ_SMS_WEBHOOK_SECRET",
        "JAZZ_WHATSAPP_WEBHOOK_SECRET",
    ],
)
def test_production_refuses_to_boot_with_any_webhook_secret_blank(missing_field):
    secrets = _real_secrets()
    secrets[missing_field] = ""
    with pytest.raises(ValueError, match=missing_field):
        Settings(ENVIRONMENT="production", **secrets)


def test_production_reports_every_missing_webhook_secret_at_once():
    with pytest.raises(ValueError) as exc_info:
        Settings(ENVIRONMENT="production", INTERNAL_API_KEY="a-real-production-key")

    message = str(exc_info.value)
    for field in (
        "AFTERSHIP_WEBHOOK_SECRET",
        "SENDGRID_WEBHOOK_SECRET",
        "JAZZ_SMS_WEBHOOK_SECRET",
        "JAZZ_WHATSAPP_WEBHOOK_SECRET",
    ):
        assert field in message


def test_staging_is_also_validated_not_just_production():
    with pytest.raises(ValueError):
        Settings(ENVIRONMENT="staging", INTERNAL_API_KEY="a-real-staging-key")
