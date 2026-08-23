# Backup & Restore

**Status:** PLANNED — the platform-wide (beyond just the database) view of the gap documented in [`../07-database/135-database-backup-recovery.md`](../07-database/135-database-backup-recovery.md).

## What needs backing up, beyond the primary database

| Component | Backup consideration | Documented status |
|---|---|---|
| PostgreSQL (system of record) | RDS automated snapshots — assumed enabled, not confirmed configured | See [`../07-database/135-database-backup-recovery.md`](../07-database/135-database-backup-recovery.md) |
| Redis | Session/cache data is inherently ephemeral (losing it degrades UX — forced re-login — but isn't data loss in the durability sense); queue contents (BullMQ jobs) losing state mid-processing is a real concern | Not documented |
| S3 (contracts, KYC images, screenshots) | Contract PDFs and KYC documents are legally/compliance-relevant records (7-year NADRA retention citation) — losing these has real regulatory consequence, distinct from a typical "just restore from backup and move on" scenario | Not documented — S3 versioning/cross-region replication status unconfirmed |
| Secrets (AWS Secrets Manager) | Presumably covered by AWS's own durability guarantees, but the *ExternalSecrets sync state* in Kubernetes should be confirmed recoverable independently | Not documented |

## The S3 contract/KYC-document case deserves special attention

Given `murabaha_contracts.contract_pdf_s3` and `contract_hash` exist specifically so a signed contract can be verified anytime (per [`../04-shariah/17-shariah-product-structure.md`](../04-shariah/17-shariah-product-structure.md)), losing these S3 objects would undermine the platform's own compliance/audit story even if the database record referencing them survives — a database row pointing to a missing S3 object is worse than either being fully lost together, since it looks like the record exists while the actual evidence doesn't. Recommend S3 versioning and cross-region replication be confirmed/enabled specifically for the contracts and KYC-images buckets, even if other buckets (e.g., static assets) don't warrant the same rigor.

## Related documents

[`../07-database/135-database-backup-recovery.md`](../07-database/135-database-backup-recovery.md), [`161-disaster-recovery.md`](161-disaster-recovery.md).
