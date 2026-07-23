"""Add virtual_cards.encryption_key_version for versioned VCN PAN/CVV encryption

Revision ID: 071
Revises: 070
Create Date: 2026-07-08 00:00:00.000000

VcnService previously encrypted PAN/CVV with a single static Fernet key
derived from settings.VCN_ENCRYPTION_KEY, cached module-globally
(_fernet_instance) with no key rotation and no way to tell, at decrypt time,
which key a given ciphertext was produced with. One leaked key decrypted
every VCN ever issued, forever.

This migration adds `encryption_key_version` to virtual_cards so each row
records which key version (e.g. "v1", "v2", ...) was used to produce its
encrypted_pan/encrypted_cvv — see VcnKeyProvider in
apps/payment-orchestrator/src/services/vcn_encryption.py. New encryptions
always use the current version (VCN_ENCRYPTION_KEY_CURRENT_VERSION);
decryption looks up the version stamped on the row. Existing rows predate
this column and are left NULL — VcnKeyProvider treats NULL as the legacy
"v1" key, which is the only key that ever existed before this change, so no
backfill is required.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '071'
down_revision: Union[str, None] = '070'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "virtual_cards",
        sa.Column("encryption_key_version", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("virtual_cards", "encryption_key_version")
