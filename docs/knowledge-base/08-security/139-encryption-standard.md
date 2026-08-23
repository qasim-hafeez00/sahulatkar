# Encryption Standard

**Status:** STABLE

## At rest

`pgcrypto` AES-256, applied at the **column level** (not just full-disk/volume encryption) to specifically: CNIC, IBANs, VCN PAN/CVV/expiry, and admin MFA secrets. This column-level approach means even a database-level compromise (e.g., a leaked backup, an over-permissioned read replica) wouldn't expose these fields in plaintext without also compromising the encryption key.

## In transit

TLS at the ingress (NGINX). Internal service-to-service traffic is expected to run within the cluster's private network — not independently confirmed whether internal traffic is also TLS-encrypted in-cluster or relies solely on network isolation; recommend confirming, since defense-in-depth would suggest encrypting internal traffic too rather than trusting network segmentation alone.

## Key management

KMS-referenced for encryption keys (per `docs/System-md-files/00Sahulatkar-System.md`'s infrastructure table and the Terraform `kms/` module) — specific key-rotation policy for the KMS keys themselves (as distinct from the application secrets covered in [`138-secrets-management.md`](138-secrets-management.md)) is not documented.

## Hashing (distinct from encryption — one-way, not reversible)

- Passwords: bcrypt, cost factor 12.
- Session tokens: SHA-256 (`access_token_hash`, `refresh_token_hash`).
- OTP codes: SHA-256 (stored as `otp_hash` on contract-signing audit records; presumably also for login OTPs).
- Contract PDFs: SHA-256 for integrity verification (not confidentiality — this hash is used to detect tampering, not to hide the content).

## What is explicitly never logged, regardless of encryption status

VCN PAN/CVV — masked (`**** **** **** 1234`) in every log/output, an immutable platform rule independent of the fact that the underlying data is also encrypted at rest. This is a defense-in-depth choice: even if encryption were somehow bypassed, the masking rule is a second, independent control against exposure via logs.

## Related documents

[`27-security-architecture.md`](27-security-architecture.md), [`138-secrets-management.md`](138-secrets-management.md), [`../07-database/25-database-architecture.md`](../07-database/25-database-architecture.md).
