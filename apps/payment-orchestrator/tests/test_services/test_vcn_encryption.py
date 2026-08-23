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
  - the production AWS KMS envelope path (P0-02): generates a data key once
    per version, persists only its KMS-encrypted form, rehydrates it on
    later calls (same or different VcnKeyProvider instance) via a fake
    boto3-shaped KMS client — mirrors the FakeSecretsManagerClient
    convention in packages/shared-python/tests/test_secrets_manager.py so
    this suite never makes a real AWS call.
"""
import pytest

import src.services.vcn_encryption as vcn_encryption_module
from src.config import settings
from src.services.vcn_encryption import UnknownEncryptionKeyVersionError, VcnKeyProvider

pytestmark = pytest.mark.asyncio


class FakeKMSClient:
    """Minimal stand-in for boto3's KMS client — one data key per KeyId, no network."""

    def __init__(self):
        self.data_keys: dict[bytes, bytes] = {}  # ciphertext -> plaintext
        self.generate_calls = 0
        self.decrypt_calls = 0

    def generate_data_key(self, KeyId: str, KeySpec: str):
        self.generate_calls += 1
        # 32 raw bytes (AES_256), distinct per call so a test can tell two
        # generated keys apart if it ever needs to.
        plaintext = f"plaintext-key-{self.generate_calls}".encode().ljust(32, b"0")[:32]
        ciphertext = f"kms-ciphertext-{self.generate_calls}".encode()
        self.data_keys[ciphertext] = plaintext
        return {"Plaintext": plaintext, "CiphertextBlob": ciphertext}

    def decrypt(self, CiphertextBlob: bytes, KeyId: str):
        self.decrypt_calls += 1
        if CiphertextBlob not in self.data_keys:
            raise ValueError(f"Unknown CiphertextBlob for KMS decrypt: {CiphertextBlob!r}")
        return {"Plaintext": self.data_keys[CiphertextBlob]}


@pytest.fixture(autouse=True)
def clear_kms_client_cache():
    # Only clear at setup: `monkeypatch` (used by _patch_kms_client below)
    # already restores the real _get_kms_client at its own teardown, and
    # relative fixture-teardown order isn't guaranteed against monkeypatch's
    # — calling .cache_clear() post-yield can hit a still-patched plain
    # lambda that has no such method.
    vcn_encryption_module._get_kms_client.cache_clear()
    yield


def _patch_kms_client(monkeypatch, fake_client: FakeKMSClient) -> None:
    monkeypatch.setattr(vcn_encryption_module, "_get_kms_client", lambda region: fake_client)


async def test_encrypt_decrypt_roundtrip_current_version(monkeypatch):
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY", "roundtrip-secret-v1")
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY_CURRENT_VERSION", "v1")

    provider = VcnKeyProvider()
    ciphertext, version = await provider.encrypt("4242424242424242")

    assert version == "v1"
    assert ciphertext != b"4242424242424242"
    assert await provider.decrypt(ciphertext, version) == "4242424242424242"


async def test_old_ciphertext_still_decrypts_after_rotation(monkeypatch):
    # Encrypt under v1 (today's current version).
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY", "old-secret-v1")
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY_V2", "new-secret-v2")
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY_CURRENT_VERSION", "v1")

    provider = VcnKeyProvider()
    old_ciphertext, old_version = await provider.encrypt("123")
    assert old_version == "v1"

    # Rotate: bump the current version. A fresh provider instance simulates
    # a new VcnService built after the settings change (VcnService builds a
    # new VcnKeyProvider per instance precisely so rotation takes effect
    # without a process restart — see VcnService.__init__).
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY_CURRENT_VERSION", "v2")
    rotated_provider = VcnKeyProvider()

    new_ciphertext, new_version = await rotated_provider.encrypt("456")
    assert new_version == "v2"
    assert await rotated_provider.decrypt(new_ciphertext, new_version) == "456"

    # The OLD ciphertext + its recorded version tag must still decrypt
    # correctly even though new encryptions now use v2.
    assert await rotated_provider.decrypt(old_ciphertext, old_version) == "123"


async def test_legacy_null_version_treated_as_v1(monkeypatch):
    """Rows written before `encryption_key_version` existed have NULL there;
    VcnKeyProvider must treat that as the legacy 'v1' key."""
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY", "legacy-secret")
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY_CURRENT_VERSION", "v1")

    provider = VcnKeyProvider()
    ciphertext, version = await provider.encrypt("legacy-value")
    assert version == "v1"

    assert await provider.decrypt(ciphertext, None) == "legacy-value"


async def test_unknown_key_version_fails_safely(monkeypatch):
    """Decrypting a ciphertext stamped with a version that has no configured
    key material must raise a clear error, not silently corrupt/misdecrypt."""
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY", "v1-secret")
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY_CURRENT_VERSION", "v1")

    provider = VcnKeyProvider()
    ciphertext, _ = await provider.encrypt("789")

    with pytest.raises(UnknownEncryptionKeyVersionError):
        await provider.decrypt(ciphertext, "v99")


async def test_wrong_key_for_recorded_version_fails_safely(monkeypatch):
    """If the secret configured for a version has since changed (e.g. a
    misconfigured rotation reused a version name with different key
    material), decrypt must raise rather than return garbage plaintext."""
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY", "secret-a")
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY_CURRENT_VERSION", "v1")
    provider = VcnKeyProvider()
    ciphertext, version = await provider.encrypt("999")

    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY", "secret-b")
    other_provider = VcnKeyProvider()
    with pytest.raises(UnknownEncryptionKeyVersionError):
        await other_provider.decrypt(ciphertext, version)


async def test_missing_secret_outside_local_raises(monkeypatch):
    """Outside the local environment, an unconfigured key version must raise
    — never silently fall back to the local-dev key — mirroring the
    pre-existing _get_fernet() behaviour this replaces."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "staging")
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY", "")
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY_CURRENT_VERSION", "v1")

    provider = VcnKeyProvider()
    with pytest.raises(RuntimeError):
        await provider.encrypt("value")


async def test_production_without_kms_arn_uses_local_derivation(monkeypatch):
    """Production without KMS_KEY_ARN set keeps today's behaviour: a real
    secret via VCN_ENCRYPTION_KEY, SHA-256-derived locally — no KMS call
    attempted."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "KMS_KEY_ARN", None)
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY", "prod-secret")
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY_CURRENT_VERSION", "v1")

    provider = VcnKeyProvider()
    ciphertext, version = await provider.encrypt("prod-value")
    assert await provider.decrypt(ciphertext, version) == "prod-value"


async def test_kms_path_without_db_raises_clear_wiring_error(monkeypatch):
    """A VcnKeyProvider built with no db (the old signature) hitting the KMS
    path must fail with an actionable error, not an AttributeError deep in
    boto3 — this is a wiring bug (VcnService always passes db) but must fail
    loudly if it ever happens."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "KMS_KEY_ARN", "arn:aws:kms:ap-south-1:123456789012:key/mock")
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY_CURRENT_VERSION", "v1")

    provider = VcnKeyProvider()  # no db
    with pytest.raises(UnknownEncryptionKeyVersionError):
        await provider.encrypt("value")


async def test_kms_path_generates_data_key_once_and_persists_ciphertext(monkeypatch, db_session):
    """First encrypt for a version calls kms:GenerateDataKey and persists the
    CiphertextBlob; a second encrypt for the SAME version (same provider,
    in-memory cache) must not call KMS again."""
    from sqlalchemy import select
    from sk_shared.models.payment import VcnKmsKeyVersion

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "KMS_KEY_ARN", "arn:aws:kms:ap-south-1:123456789012:key/mock")
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY_CURRENT_VERSION", "v1")

    fake_kms = FakeKMSClient()
    _patch_kms_client(monkeypatch, fake_kms)

    provider = VcnKeyProvider(db=db_session)
    ciphertext, version = await provider.encrypt("4111111111111111")
    assert version == "v1"
    assert await provider.decrypt(ciphertext, version) == "4111111111111111"
    assert fake_kms.generate_calls == 1

    # Second value under the same version — cached cipher, no new KMS call.
    ciphertext2, _ = await provider.encrypt("4222222222222222")
    assert await provider.decrypt(ciphertext2, "v1") == "4222222222222222"
    assert fake_kms.generate_calls == 1

    row = await db_session.scalar(select(VcnKmsKeyVersion).where(VcnKmsKeyVersion.version == "v1"))
    assert row is not None
    assert row.kms_key_arn == settings.KMS_KEY_ARN


async def test_kms_path_rehydrates_data_key_for_fresh_provider(monkeypatch, db_session):
    """A second VcnKeyProvider instance (simulating a different process/pod)
    must rehydrate the SAME plaintext data key via kms:Decrypt against the
    persisted row, not generate a new one — otherwise ciphertext written by
    one pod couldn't be read by another."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "KMS_KEY_ARN", "arn:aws:kms:ap-south-1:123456789012:key/mock")
    monkeypatch.setattr(settings, "VCN_ENCRYPTION_KEY_CURRENT_VERSION", "v1")

    fake_kms = FakeKMSClient()
    _patch_kms_client(monkeypatch, fake_kms)

    writer = VcnKeyProvider(db=db_session)
    ciphertext, version = await writer.encrypt("5500005555555559")
    await db_session.commit()
    assert fake_kms.generate_calls == 1

    reader = VcnKeyProvider(db=db_session)  # fresh instance, empty cipher cache
    plaintext = await reader.decrypt(ciphertext, version)

    assert plaintext == "5500005555555559"
    assert fake_kms.generate_calls == 1  # no second data key generated
    assert fake_kms.decrypt_calls == 1  # rehydrated via kms:Decrypt instead
