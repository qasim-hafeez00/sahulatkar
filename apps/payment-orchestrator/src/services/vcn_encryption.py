"""
Versioned envelope encryption for VCN PAN/CVV data.

Why versioned
-------------
`VcnService` previously encrypted every PAN/CVV with a single static Fernet
key derived from `settings.VCN_ENCRYPTION_KEY`, cached module-globally. One
leaked key decrypted every VCN ever issued, forever, with no way to rotate
without losing access to already-encrypted rows.

Scheme
------
Every ciphertext is paired with a short version tag ("v1", "v2", ...)
persisted alongside it (`VirtualCard.encryption_key_version`). Encryption
always uses the *current* version (`VcnKeyProvider.current_version`, driven
by `settings.VCN_ENCRYPTION_KEY_CURRENT_VERSION`); decryption looks up
whichever version tag is stored on the row, so old ciphertext keeps
decrypting correctly after the current version is bumped ("rotated") —
rotation does not require re-encrypting historical rows immediately.

Rows written before this column existed have `encryption_key_version IS
NULL` in the DB; those are treated as `LEGACY_VERSION` ("v1"), which is the
only version that ever existed before this change.

For actually moving old rows onto the newest key (freeing up retirement of
an old key's secret), see the offline batch-rotation script at
apps/payment-orchestrator/scripts/rotate_vcn_encryption_keys.py — lazy
per-row rotation is intentionally NOT done as a side effect of `decrypt()`
here, since VCN plaintext is only ever read transiently for checkout and we
don't want a read path silently issuing writes.

Local-mock vs. production-KMS split
------------------------------------
Local / non-production (default): each version's key material is a plain
string setting (`VCN_ENCRYPTION_KEY` for "v1", `VCN_ENCRYPTION_KEY_V2` for
"v2", `VCN_ENCRYPTION_KEY_V3` for "v3") SHA-256-hashed into a 32-byte Fernet
key. This mirrors the local-mock half of `apps/gateway/src/core/kms.py`'s
`KMSProvider` (mock key material now, swappable for a managed KMS later
without changing callers), and requires no real AWS access to run tests.

Production (`ENVIRONMENT=production`) with `KMS_KEY_ARN` set: intended to
route new encryptions through AWS KMS envelope encryption (generate a data
key via `kms:GenerateDataKey`, use it to encrypt the PAN/CVV, store the
KMS-encrypted data key alongside so it can be unwrapped via `kms:Decrypt` at
read time) instead of a static local secret. NOT implemented — see
`_kms_get_cipher()` below — because it needs a real AWS KMS endpoint to
exercise, and `boto3` is not currently a payment-orchestrator dependency.
Implementing it here would mean hand-rolling untestable AWS calls, which the
task deliberately avoids in favor of a clearly-marked stub. The public
interface (`get_cipher`/`encrypt`/`decrypt`) is stable across both paths, so
wiring in the real KMS calls later is a non-breaking swap.

Production without `KMS_KEY_ARN` set (today's default) keeps behaving
exactly as before this change: a real secret must be provided via
`VCN_ENCRYPTION_KEY`/`VCN_ENCRYPTION_KEY_V2`/... (SHA-256-derived, same as
local) or startup fails — see `_local_secret_for_version`.
"""
from __future__ import annotations

import base64
import hashlib
import logging
from typing import ClassVar, Optional

from cryptography.fernet import Fernet, InvalidToken

from src.config import settings

logger = logging.getLogger(__name__)


class UnknownEncryptionKeyVersionError(RuntimeError):
    """Raised when a ciphertext references a key version we have no key material for,
    or when a ciphertext fails to decrypt under its recorded version's key.

    This is a fail-closed error: decryption never silently falls back to a
    different key or returns partially-decrypted / corrupted data.
    """


class VcnKeyProvider:
    """Resolves Fernet ciphers by version tag for VCN PAN/CVV envelope encryption."""

    # Rows written before `encryption_key_version` existed have that column as
    # NULL. There was only ever one key in use at that time — treat NULL as
    # this version.
    LEGACY_VERSION: ClassVar[str] = "v1"

    def __init__(self) -> None:
        self._cipher_cache: dict[str, Fernet] = {}

    @property
    def current_version(self) -> str:
        return settings.VCN_ENCRYPTION_KEY_CURRENT_VERSION

    def encrypt(self, value: str) -> tuple[bytes, str]:
        """Encrypt with the current key version. Returns (ciphertext, version_tag)."""
        version = self.current_version
        cipher = self.get_cipher(version)
        return cipher.encrypt(value.encode("utf-8")), version

    def decrypt(self, ciphertext: bytes, version: Optional[str]) -> str:
        """Decrypt using the key version stamped on the record.

        `version` may be None for rows written before this column existed —
        those are treated as `LEGACY_VERSION` ("v1").
        """
        resolved_version = version or self.LEGACY_VERSION
        cipher = self.get_cipher(resolved_version)
        try:
            return cipher.decrypt(ciphertext).decode("utf-8")
        except InvalidToken as exc:
            raise UnknownEncryptionKeyVersionError(
                f"Failed to decrypt VCN field with key version '{resolved_version}' — "
                "ciphertext does not match this key (wrong/rotated key material, or "
                "corrupted data). Refusing to guess at another key."
            ) from exc

    def get_cipher(self, version: str) -> Fernet:
        cached = self._cipher_cache.get(version)
        if cached is not None:
            return cached

        if settings.ENVIRONMENT == "production" and settings.KMS_KEY_ARN:
            cipher = self._kms_get_cipher(version)
        else:
            cipher = self._local_get_cipher(version)

        self._cipher_cache[version] = cipher
        return cipher

    # ── Local / mock key derivation ─────────────────────────────────────────

    def _local_get_cipher(self, version: str) -> Fernet:
        secret = self._local_secret_for_version(version)
        if not secret:
            raise UnknownEncryptionKeyVersionError(
                f"No VCN encryption key configured for version '{version}'. Known "
                "versions are sourced from VCN_ENCRYPTION_KEY (v1), "
                "VCN_ENCRYPTION_KEY_V2 (v2), VCN_ENCRYPTION_KEY_V3 (v3) — set the "
                "matching env var, or fix VCN_ENCRYPTION_KEY_CURRENT_VERSION if it "
                "points at a version that was never configured."
            )
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
        return Fernet(key)

    def _local_secret_for_version(self, version: str) -> Optional[str]:
        version_map: dict[str, str] = {
            "v1": settings.VCN_ENCRYPTION_KEY,
            "v2": settings.VCN_ENCRYPTION_KEY_V2,
            "v3": settings.VCN_ENCRYPTION_KEY_V3,
        }
        secret = version_map.get(version)

        if not secret and version == self.LEGACY_VERSION and settings.ENVIRONMENT == "local":
            # Local-dev fallback so nothing requires real secrets to run locally/in tests.
            secret = "local-dev-vcn-key"

        if not secret and settings.ENVIRONMENT != "local":
            raise RuntimeError(
                f"VCN encryption key for version '{version}' is required outside the "
                "local environment (set VCN_ENCRYPTION_KEY / VCN_ENCRYPTION_KEY_V2 / "
                "VCN_ENCRYPTION_KEY_V3 as appropriate)."
            )

        return secret or None

    # ── Production KMS envelope path (TODO — not implemented) ──────────────

    def _kms_get_cipher(self, version: str) -> Fernet:
        """
        TODO(production-kms): route through AWS KMS envelope encryption instead
        of a static locally-derived secret.

        Intended shape (mirrors apps/gateway/src/core/kms.py's documented
        local-mock -> real-KMS swap):

            import boto3
            client = boto3.client("kms", region_name="ap-south-1")
            # One data key per version, generated once via GenerateDataKey and
            # cached (plaintext data key held in memory only; the
            # KMS-encrypted CiphertextBlob is what gets persisted, e.g. in a
            # small `vcn_key_versions` table keyed by version tag):
            resp = client.generate_data_key(KeyId=settings.KMS_KEY_ARN, KeySpec="AES_256")
            plaintext_data_key = resp["Plaintext"]
            encrypted_data_key = resp["CiphertextBlob"]  # persist alongside `version`
            key = base64.urlsafe_b64encode(plaintext_data_key)
            return Fernet(key)

            # To rehydrate an existing version's cipher on a fresh process:
            plaintext_data_key = client.decrypt(CiphertextBlob=encrypted_data_key)["Plaintext"]

        This isn't implemented because it requires real AWS KMS access to
        exercise (untestable in this environment) and `boto3` is not
        currently a payment-orchestrator dependency — half-implementing it
        would ship unverified AWS calls. Do not set `KMS_KEY_ARN` in
        production until this lands; leave it unset to keep using the
        `VCN_ENCRYPTION_KEY*`-derived local path (see `_local_get_cipher`),
        which remains fully supported.
        """
        raise NotImplementedError(
            "AWS KMS envelope encryption for VCN keys is not implemented yet "
            f"(requested version '{version}'). KMS_KEY_ARN is set, which signals a "
            "production KMS rollout is intended, but the envelope-encryption "
            "plumbing has not been built — see the TODO block in "
            "VcnKeyProvider._kms_get_cipher for the intended design. Until this "
            "lands, unset KMS_KEY_ARN to keep using the VCN_ENCRYPTION_KEY*-derived "
            "local path."
        )
