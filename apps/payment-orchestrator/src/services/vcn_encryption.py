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
import os
from functools import lru_cache
from typing import ClassVar, Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.payment import VcnKmsKeyVersion

from src.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=None)
def _get_kms_client(region: str):
    """Return a cached boto3 KMS client for `region`.

    Mirrors sk_shared.secrets_manager._get_secretsmanager_client: lazy import
    (boto3 is only needed on this path — real production, KMS_KEY_ARN set),
    cached per-region so repeated calls in the same process reuse one client.
    """
    import boto3  # Lazy: only imported when the production KMS path is actually taken.

    return boto3.client("kms", region_name=region)


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

    def __init__(self, db: Optional[AsyncSession] = None) -> None:
        self._cipher_cache: dict[str, Fernet] = {}
        # Only required by the production KMS path (_kms_get_cipher), which
        # persists/rehydrates the per-version encrypted data key. The local
        # path never touches `db`.
        self.db = db

    @property
    def current_version(self) -> str:
        return settings.VCN_ENCRYPTION_KEY_CURRENT_VERSION

    async def encrypt(self, value: str) -> tuple[bytes, str]:
        """Encrypt with the current key version. Returns (ciphertext, version_tag)."""
        version = self.current_version
        cipher = await self.get_cipher(version)
        return cipher.encrypt(value.encode("utf-8")), version

    async def decrypt(self, ciphertext: bytes, version: Optional[str]) -> str:
        """Decrypt using the key version stamped on the record.

        `version` may be None for rows written before this column existed —
        those are treated as `LEGACY_VERSION` ("v1").
        """
        resolved_version = version or self.LEGACY_VERSION
        cipher = await self.get_cipher(resolved_version)
        try:
            return cipher.decrypt(ciphertext).decode("utf-8")
        except InvalidToken as exc:
            raise UnknownEncryptionKeyVersionError(
                f"Failed to decrypt VCN field with key version '{resolved_version}' — "
                "ciphertext does not match this key (wrong/rotated key material, or "
                "corrupted data). Refusing to guess at another key."
            ) from exc

    async def get_cipher(self, version: str) -> Fernet:
        cached = self._cipher_cache.get(version)
        if cached is not None:
            return cached

        if settings.ENVIRONMENT == "production" and settings.KMS_KEY_ARN:
            cipher = await self._kms_get_cipher(version)
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

    # ── Production KMS envelope path ────────────────────────────────────────

    async def _kms_get_cipher(self, version: str) -> Fernet:
        """AWS KMS envelope encryption: one data key per version.

        First call for a given version calls kms:GenerateDataKey and persists
        the KMS-encrypted CiphertextBlob in `vcn_kms_key_versions` (the
        plaintext data key is never persisted — only held in memory for this
        process's cipher cache). Every later call, in this or any other
        process, rehydrates the same plaintext data key via kms:Decrypt
        against the persisted CiphertextBlob, so ciphertext produced by one
        pod stays decryptable by every other pod/process without needing a
        shared in-memory cache.
        """
        if self.db is None:
            raise UnknownEncryptionKeyVersionError(
                f"VcnKeyProvider was constructed without a db session — cannot use "
                f"the production KMS path for version '{version}'. This is a wiring "
                "bug: pass `db` when ENVIRONMENT=production and KMS_KEY_ARN is set."
            )

        region = os.getenv("AWS_REGION", "ap-south-1")
        client = _get_kms_client(region)

        row = await self.db.scalar(
            select(VcnKmsKeyVersion).where(VcnKmsKeyVersion.version == version)
        )

        if row is None:
            resp = client.generate_data_key(KeyId=settings.KMS_KEY_ARN, KeySpec="AES_256")
            plaintext_data_key: bytes = resp["Plaintext"]
            encrypted_data_key: bytes = resp["CiphertextBlob"]

            self.db.add(
                VcnKmsKeyVersion(
                    version=version,
                    kms_key_arn=settings.KMS_KEY_ARN,
                    encrypted_data_key=encrypted_data_key,
                )
            )
            try:
                await self.db.flush()
            except IntegrityError:
                # Lost a race with another process generating the same
                # version's data key concurrently — that process's row wins;
                # discard ours (never persisted, so nothing to clean up
                # KMS-side) and rehydrate from theirs instead.
                await self.db.rollback()
                row = await self.db.scalar(
                    select(VcnKmsKeyVersion).where(VcnKmsKeyVersion.version == version)
                )
                if row is None:
                    raise UnknownEncryptionKeyVersionError(
                        f"Lost a race generating the KMS data key for version "
                        f"'{version}' but the winning row is not visible — this "
                        "should not happen outside a concurrent-write bug."
                    )
                plaintext_data_key = client.decrypt(
                    CiphertextBlob=row.encrypted_data_key, KeyId=row.kms_key_arn
                )["Plaintext"]
        else:
            plaintext_data_key = client.decrypt(
                CiphertextBlob=row.encrypted_data_key, KeyId=row.kms_key_arn
            )["Plaintext"]

        key = base64.urlsafe_b64encode(plaintext_data_key)
        return Fernet(key)
