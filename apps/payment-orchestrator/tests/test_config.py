"""
Tests for src/config.py::validate_critical_settings — the boot-time guard
that refuses to start payment-orchestrator outside `local` if a real
payment-gateway credential (Stripe/Safepay/JazzCash/Raast), the VCN PAN/CVV
encryption key, or the internal service token is still at its empty
placeholder default.

Delegates to sk_shared.boot_validation.raise_if_placeholder_credentials
(packages/shared-python/sk_shared/boot_validation.py), which is already
covered directly in packages/shared-python/tests/test_boot_validation.py —
these tests only cover payment-orchestrator's wiring: which settings it
checks, and that it is actually invoked from src/main.py's lifespan startup.
"""
import pytest

from src.config import settings, validate_critical_settings

_CREDENTIAL_FIELDS = [
    "STRIPE_SECRET_KEY",
    "SAFEPAY_API_KEY",
    "SAFEPAY_API_SECRET",
    "JAZZCASH_MERCHANT_ID",
    "JAZZCASH_PASSWORD",
    "RAAST_API_KEY",
    "RAAST_API_SECRET",
    "RAAST_MERCHANT_IBAN",
    "VCN_ENCRYPTION_KEY",
    "INTERNAL_API_TOKEN",
]


@pytest.fixture
def blank_credentials(monkeypatch):
    """Reset every credential field to its empty placeholder default."""
    for field in _CREDENTIAL_FIELDS:
        monkeypatch.setattr(settings, field, "")
    yield


@pytest.fixture
def real_credentials(monkeypatch):
    for field in _CREDENTIAL_FIELDS:
        monkeypatch.setattr(settings, field, f"real-{field.lower()}-value")
    yield


def test_local_environment_boots_even_with_all_credentials_blank(monkeypatch, blank_credentials):
    monkeypatch.setattr(settings, "ENVIRONMENT", "local")
    validate_critical_settings()  # must not raise


def test_production_environment_refuses_to_boot_with_blank_stripe_key(monkeypatch, real_credentials):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_TEST_PAYMENT_FALLBACKS", False)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "")

    with pytest.raises(RuntimeError) as exc_info:
        validate_critical_settings()

    message = str(exc_info.value)
    assert "PAYMENT_ORCHESTRATOR_CONFIG_VALIDATION_FAILED" in message
    assert "STRIPE_SECRET_KEY" in message


def test_production_environment_refuses_to_boot_with_blank_vcn_encryption_key(monkeypatch, real_credentials):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_TEST_PAYMENT_FALLBACKS", False)
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY", "")

    with pytest.raises(RuntimeError) as exc_info:
        validate_critical_settings()

    assert "VCN_ENCRYPTION_KEY" in str(exc_info.value)


def test_production_environment_reports_every_missing_credential_at_once(monkeypatch, blank_credentials):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_TEST_PAYMENT_FALLBACKS", False)

    with pytest.raises(RuntimeError) as exc_info:
        validate_critical_settings()

    message = str(exc_info.value)
    for field in _CREDENTIAL_FIELDS:
        assert field in message, f"{field} should be reported as missing"


def test_production_environment_boots_cleanly_with_all_real_credentials(monkeypatch, real_credentials):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_TEST_PAYMENT_FALLBACKS", False)
    validate_critical_settings()  # must not raise


def test_staging_environment_is_also_validated_not_just_production(monkeypatch, blank_credentials):
    """boot_validation treats any non-local environment as requiring real creds, not just 'production'."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "staging")
    monkeypatch.setattr(settings, "ALLOW_TEST_PAYMENT_FALLBACKS", False)

    with pytest.raises(RuntimeError):
        validate_critical_settings()


# ── HIGH-01: ENVIRONMENT fail-open regression tests ──────────────────────────
#
# ENVIRONMENT defaults to "local", so before this fix, every gateway
# client/adapter that branched on `settings.ENVIRONMENT == "local"` alone
# would silently enable fake-success/test-PAN/skip-signature-verification
# behavior on a deploy that simply forgot to set ENVIRONMENT. These tests
# cover `Settings.test_payment_fallbacks_enabled` (the single choke point
# every such fallback now goes through) and the boot-time guard that refuses
# to let ALLOW_TEST_PAYMENT_FALLBACKS=true leak outside ENVIRONMENT=="local".

def test_fallbacks_disabled_when_environment_unset_default(monkeypatch):
    """The dangerous case: ENVIRONMENT left at its "local" default (as if a
    deploy forgot to set it) with no explicit opt-in — fallbacks must stay
    OFF, i.e. fail closed (real gateway calls, real signature checks)."""
    monkeypatch.setattr(settings, "ALLOW_TEST_PAYMENT_FALLBACKS", False)
    assert settings.ENVIRONMENT == "local"
    assert settings.test_payment_fallbacks_enabled is False


def test_fallbacks_disabled_when_flag_set_but_not_local(monkeypatch):
    """Flag alone is not enough — ENVIRONMENT must also actually be local."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_TEST_PAYMENT_FALLBACKS", True)
    assert settings.test_payment_fallbacks_enabled is False


def test_fallbacks_enabled_only_with_both_local_and_explicit_flag(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "local")
    monkeypatch.setattr(settings, "ALLOW_TEST_PAYMENT_FALLBACKS", True)
    assert settings.test_payment_fallbacks_enabled is True


def test_boot_refuses_allow_test_payment_fallbacks_outside_local(monkeypatch, real_credentials):
    """Defense in depth: even if ALLOW_TEST_PAYMENT_FALLBACKS were somehow set
    true in a non-local deploy, startup must refuse rather than silently
    carrying the insecure flag into staging/production."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_TEST_PAYMENT_FALLBACKS", True)

    with pytest.raises(RuntimeError) as exc_info:
        validate_critical_settings()

    assert "ALLOW_TEST_PAYMENT_FALLBACKS" in str(exc_info.value)


def test_main_lifespan_calls_validate_critical_settings_before_other_startup_work():
    """
    Wiring check: main.py's startup lifespan must call validate_critical_settings()
    before it opens Redis/DB connections or starts background workers, so a bad
    boot fails fast instead of partially starting up. We don't execute the real
    lifespan here (it opens a real Redis connection and spawns background
    worker tasks) — just confirm the call is present and ordered correctly in
    source, mirroring how gateway's main.py wires its own validate_critical_settings().
    """
    import inspect

    import src.main as main_module

    source = inspect.getsource(main_module.lifespan)
    assert "validate_critical_settings()" in source

    call_idx = source.index("validate_critical_settings()")
    redis_idx = source.index("get_redis_client(")
    assert call_idx < redis_idx, (
        "validate_critical_settings() must run before Redis/background workers start, "
        "so an invalid boot config fails fast"
    )
