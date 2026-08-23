# Security Threat Model

**Status:** STABLE — this is an engineering-derived threat inventory (built from the code audit's findings), not the output of a formal STRIDE/PASTA modeling exercise. Recommend Security formally conduct one; this document is a solid starting input for that exercise, not a replacement for it.

## Assets worth protecting, ranked by consequence of compromise

1. **VCN PAN/CVV (plaintext, in-flight to the checkout agent)** — direct financial theft capability if exposed.
2. **JWT signing key** — compromise allows forging valid session tokens for any user or admin.
3. **CNIC/KYC data** — identity-theft-enabling PII, plus regulatory exposure (see [`../11-compliance/36-compliance-requirements-matrix.md`](../11-compliance/36-compliance-requirements-matrix.md)).
4. **The ledger's write path** — compromise or bug here can fabricate or erase financial obligations.
5. **The Credit Engine's decision path** — compromise could approve fraudulent financing at scale.

## Threat-to-mitigation mapping (consolidated from findings across this knowledge base)

| Threat | Asset at risk | Current mitigation status |
|---|---|---|
| VCN-decrypt endpoint abuse (no rate limit) | #1 | **Open** (`PO-BL-01`) |
| Refresh/access token confusion | #2 | **Open** (`SH-GAP-02`) |
| Admin TOTP brute force (no lockout) | #2 | **Open** (`GW-BL-05`) |
| Unauthenticated SendGrid webhook | Notification integrity, indirectly customer trust | **Open** (`NS-BL-01`) |
| No secret rotation | #1, #2 | **Open** (`INF-GAP-07`) |
| Audit trail is mutable/deletable | Forensic capability across all assets | **Open** (`INF-GAP-08`) |
| SQL injection | #3, #4 | Mitigated (parameterized queries via SQLAlchemy) |
| Insecure internal service calls | All | Mitigated (HMAC-authenticated internal token, consistently implemented) |
| Ledger write-path logic bugs (not an external attacker, but an internal-correctness threat) | #4 | **Open** — debit=credit unvalidated (`LS-CRIT-02`) |
| Credit Engine model/logic tampering | #5 | Not independently audited (Credit Engine was out of scope for the 2026-04-27 code audit) |

## What a formal threat-modeling exercise should add

Attacker personas (opportunistic fraudster vs. sophisticated insider vs. external attacker with stolen credentials), attack trees for the top assets, and a documented risk-acceptance or remediation-timeline decision for each open item above — this document provides the raw findings; Security leadership should own turning it into a governed model with accepted risk levels.

## Related documents

[`27-security-architecture.md`](27-security-architecture.md), [`142-security-incident-response.md`](142-security-incident-response.md), `docs/PRODUCTION_GAPS_REPORT.md`.
