"""
Offline batch rotation for VCN PAN/CVV encryption keys.

Background
----------
VcnKeyProvider (src/services/vcn_encryption.py) uses a versioned key
envelope: every VirtualCard row stores which key version
(`encryption_key_version`) its `encrypted_pan`/`encrypted_cvv` were produced
with. Rotating `VCN_ENCRYPTION_KEY_CURRENT_VERSION` (e.g. "v1" -> "v2")
immediately makes all *new* VCN issuances use the new key — old rows keep
decrypting fine under their original version, so rotation itself never
requires downtime or an immediate migration.

This script is the *optional* follow-up: once a rotation has happened and
you eventually want to retire an old key's secret (e.g. it may have been the
one that leaked, prompting the rotation in the first place), every row still
stamped with that old version needs to be re-encrypted onto the current
version first. This script does that as a one-off, idempotent, offline
batch job — it is NOT run automatically by the app.

Usage
-----
Run from apps/payment-orchestrator with the service's normal environment
(DATABASE_URL, VCN_ENCRYPTION_KEY*, VCN_ENCRYPTION_KEY_CURRENT_VERSION) set,
same as running the app itself:

    python -m scripts.rotate_vcn_encryption_keys [--dry-run] [--batch-size 200]

Safety
------
- Only rows whose `encryption_key_version` (NULL treated as the legacy "v1")
  differs from the *current* version are touched.
- Each row is decrypted with its recorded key and re-encrypted with the
  current key inside its own transaction — a failure partway through only
  ever leaves already-processed rows rotated forward; it never leaves a row
  half-written (decrypt-then-encrypt happens in memory before the row is
  updated).
- `--dry-run` reports how many rows would be rotated without writing.
- Requires that the old key's secret is STILL configured (e.g.
  VCN_ENCRYPTION_KEY for "v1") at run time — you need the old key to decrypt
  before you can re-encrypt. Only remove the old secret from config after
  this script reports zero remaining rows on that version.
"""
from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import select

from sk_shared.database import SessionLocal
from sk_shared.models.payment import VirtualCard

from src.config import settings
from src.services.vcn_encryption import VcnKeyProvider

logger = logging.getLogger("rotate_vcn_encryption_keys")


async def rotate(batch_size: int = 200, dry_run: bool = False) -> int:
    current_version = VcnKeyProvider().current_version
    rotated_count = 0

    async with SessionLocal() as session:
        # Bound to this session so the production-KMS path (if active) can
        # persist/rehydrate per-version data keys via vcn_kms_key_versions.
        key_provider = VcnKeyProvider(db=session)
        offset = 0
        while True:
            result = await session.execute(
                select(VirtualCard)
                .where(VirtualCard.deleted_at.is_(None))
                .order_by(VirtualCard.id)
                .offset(offset)
                .limit(batch_size)
            )
            cards = result.scalars().all()
            if not cards:
                break

            for card in cards:
                stamped_version = card.encryption_key_version or VcnKeyProvider.LEGACY_VERSION
                if stamped_version == current_version:
                    continue  # already on the current key

                if dry_run:
                    rotated_count += 1
                    continue

                plaintext_pan = await key_provider.decrypt(card.encrypted_pan, card.encryption_key_version)
                plaintext_cvv = await key_provider.decrypt(card.encrypted_cvv, card.encryption_key_version)

                new_encrypted_pan, new_version = await key_provider.encrypt(plaintext_pan)
                new_encrypted_cvv, _ = await key_provider.encrypt(plaintext_cvv)

                card.encrypted_pan = new_encrypted_pan
                card.encrypted_cvv = new_encrypted_cvv
                card.encryption_key_version = new_version
                rotated_count += 1

            if not dry_run:
                await session.commit()
            offset += batch_size

    verb = "Would rotate" if dry_run else "Rotated"
    logger.info("%s %d VirtualCard row(s) onto key version '%s'", verb, rotated_count, current_version)
    return rotated_count


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing")
    parser.add_argument("--batch-size", type=int, default=200, help="Rows fetched/committed per batch")
    args = parser.parse_args()

    if settings.ENVIRONMENT == "production" and not args.dry_run:
        confirm = input(
            f"About to rotate VirtualCard rows in PRODUCTION to key version "
            f"'{settings.VCN_ENCRYPTION_KEY_CURRENT_VERSION}'. Type 'yes' to continue: "
        )
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            return

    asyncio.run(rotate(batch_size=args.batch_size, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
