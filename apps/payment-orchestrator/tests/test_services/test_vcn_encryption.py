"""
Unit tests for VcnKeyProvider — versioned envelope encryption for VCN PAN/CVV.

Covers:
  - encrypt-then-decrypt roundtrip under the current key version
  - old ciphertext (encrypted under an older version) still decrypts
    correctly after the current version is "rotated" forward
  - a NULL (legacy, pre-versioning) version tag is treated as "v1"
  - decrypting with a key version that has no configured key material, or
    the wrong key material for its recorded version, fails with a clear,
    specific error rather than silently returning corrupted plaintext
  - outside the local environment, an unconfigured key still hard-fails
    (no insecure fallback to a dev key), matching the pre-existing
    _get_fernet() behaviour this replaces
"""
import pytest

from src.config import settings
from src.services.vcn_encryption import UnknownEncryptionKeyVersionError, VcnKeyProvider


def test_encrypt_decrypt_roundtrip_current_version(monkeypatch):
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY", "roundtrip-secret-v1")
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY_CURRENT_VERSION", "v1")

    provider = VcnKeyProvider()
    ciphertext, version = provider.encrypt("4242424242424242")

    assert version == "v1"
    assert ciphertext != b"4242424242424242"
    assert provider.decrypt(ciphertext, version) == "4242424242424242"


def test_old_ciphertext_still_decrypts_after_rotation(monkeypatch):
    # Encrypt under v1 (today's current version).
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY", "old-secret-v1")
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY_V2", "new-secret-v2")
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY_CURRENT_VERSION", "v1")

    provider = VcnKeyProvider()
    old_ciphertext, old_version = provider.encrypt("123")
    assert old_version == "v1"

    # Rotate: bump the current version. A fresh provider instance simulates
    # a new VcnService built after the settings change (VcnService builds a
    # new VcnKeyProvider per instance precisely so rotation takes effect
    # without a process restart — see VcnService.__init__).
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY_CURRENT_VERSION", "v2")
    rotated_provider = VcnKeyProvider()

    new_ciphertext, new_version = rotated_provider.encrypt("456")
    assert new_version == "v2"
    assert rotated_provider.decrypt(new_ciphertext, new_version) == "456"

    # The OLD ciphertext + its recorded version tag must still decrypt
    # correctly even though new encryptions now use v2.
    assert rotated_provider.decrypt(old_ciphertext, old_version) == "123"


def test_legacy_null_version_treated_as_v1(monkeypatch):
    """Rows written before `encryption_key_version` existed have NULL there;
    VcnKeyProvider must treat that as the legacy 'v1' key."""
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY", "legacy-secret")
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY_CURRENT_VERSION", "v1")

    provider = VcnKeyProvider()
    ciphertext, version = provider.encrypt("legacy-value")
    assert version == "v1"

    assert provider.decrypt(ciphertext, None) == "legacy-value"


def test_unknown_key_version_fails_safely(monkeypatch):
    """Decrypting a ciphertext stamped with a version that has no configured
    key material must raise a clear error, not silently corrupt/misdecrypt."""
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY", "v1-secret")
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY_CURRENT_VERSION", "v1")

    provider = VcnKeyProvider()
    ciphertext, _ = provider.encrypt("789")

    with pytest.raises(UnknownEncryptionKeyVersionError):
        provider.decrypt(ciphertext, "v99")


def test_wrong_key_for_recorded_version_fails_safely(monkeypatch):
    """If the secret configured for a version has since changed (e.g. a
    misconfigured rotation reused a version name with different key
    material), decrypt must raise rather than return garbage plaintext."""
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY", "secret-a")
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY_CURRENT_VERSION", "v1")
    provider = VcnKeyProvider()
    ciphertext, version = provider.encrypt("999")

    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY", "secret-b")
    other_provider = VcnKeyProvider()
    with pytest.raises(UnknownEncryptionKeyVersionError):
        other_provider.decrypt(ciphertext, version)


def test_missing_secret_outside_local_raises(monkeypatch):
    """Outside the local environment, an unconfigured key version must raise
    — never silently fall back to the local-dev key — mirroring the
    pre-existing _get_fernet() behaviour this replaces."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "staging")
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY", "")
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY_CURRENT_VERSION", "v1")

    provider = VcnKeyProvider()
    with pytest.raises(RuntimeError):
        provider.encrypt("value")


def test_production_without_kms_arn_uses_local_derivation(monkeypatch):
    """Production without KMS_KEY_ARN set keeps today's behaviour: a real
    secret via VCN_ENCRYPTION_KEY, SHA-256-derived locally — no KMS call
    attempted."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "KMS_KEY_ARN", None)
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY", "prod-secret")
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY_CURRENT_VERSION", "v1")

    provider = VcnKeyProvider()
    ciphertext, version = provider.encrypt("prod-value")
    assert provider.decrypt(ciphertext, version) == "prod-value"


def test_production_with_kms_arn_raises_not_implemented(monkeypatch):
    """Setting KMS_KEY_ARN in production routes to the (intentionally
    unimplemented) KMS envelope path, which must fail loudly with a clear
    TODO rather than silently using the wrong crypto."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "KMS_KEY_ARN", "arn:aws:kms:ap-south-1:123456789012:key/mock")
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY_CURRENT_VERSION", "v1")

    provider = VcnKeyProvider()
    with pytest.raises(NotImplementedError):
        provider.encrypt("value")
