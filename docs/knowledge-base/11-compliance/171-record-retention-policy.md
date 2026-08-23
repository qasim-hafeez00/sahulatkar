# Record Retention Policy

> **STATUS: INTERNAL DRAFT.**

## What's specified (partial, incident-by-incident, not a unified policy)

| Record type | Retention | Source |
|---|---|---|
| NADRA raw response (KYC) | 7 years | Cited as a SECP requirement in `docs/System-md-files/M02-kyc.md` — citation not independently verified |
| KYC images (CNIC, selfie) | 1 year on S3 standard, then Glacier (implies longer-term but colder storage, not deletion) | `docs/System-md-files/M02-kyc.md` |
| `tracking_events` (delivery) | 2 years, compressed after 7 days | `docs/System-md-files/M10-M12-delivery-ledger-admin.md` |
| Credit limit history | Immutable, presumably indefinite (no expiry documented) | `docs/System-md-files/M04-credit-engine.md` |
| Audit trails | Not documented — and currently stored in a mutable/deletable table regardless (`INF-GAP-08`), which is itself a retention-integrity problem, not just a duration question |
| Journal entries / ledger records | Not documented — presumably indefinite given accounting/audit norms, but not stated explicitly anywhere |
| Contract PDFs (Wakalah, Murabaha) | Not documented — presumably tied to the loan's life plus some post-completion window, but no explicit retention period specified |

## What's missing: a unified policy, not just scattered retention periods

Each row above was specified locally, by whichever module happened to need a retention decision — there's no single document stating the company's overall record-retention philosophy (what gets kept, for how long, and why, mapped against actual regulatory citations rather than each team independently guessing). This matters because retention periods that were set independently, without cross-checking, risk being inconsistent in ways that matter (e.g., is 7 years the right period specifically because of the NADRA citation, or should *other* KYC-adjacent records also be 7 years for the same underlying reason, and if so, are they?).

## Recommended action

Compliance should author a single Record Retention Policy that: (1) states the actual regulatory basis for each retention period (confirming or correcting the NADRA 7-year citation specifically), (2) covers every record type not yet addressed above (contracts, journal entries, audit trails), and (3) specifies the deletion/archival mechanism for when a retention period actually expires — nothing in current engineering docs describes what happens to a KYC image or NADRA response *after* its retention period ends.

## Related documents

[`169-data-protection-compliance.md`](169-data-protection-compliance.md), [`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md).
