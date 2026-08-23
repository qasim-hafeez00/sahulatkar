# Security Incident Response

**Status:** PLANNED — the security-specific slice of [`../12-operations/41-incident-response-plan.md`](../12-operations/41-incident-response-plan.md), given its own document since security incidents (as opposed to financial or operational ones) warrant a distinct response shape (containment, forensics, disclosure obligations).

## Why this needs to be distinct from general incident response

A security incident's response priorities differ from an operational one: **contain and preserve evidence first**, restore service second — the opposite order priority from, say, a scraping-worker crash, where restoring service is usually the only priority. Given [`../07-database/25-database-architecture.md`](../07-database/25-database-architecture.md) notes the `audit_trails` table is mutable/deletable (`INF-GAP-08`), evidence preservation specifically needs a documented, practiced step (e.g., immediately snapshotting relevant logs/DB state to immutable storage) rather than being assumed to happen naturally.

## Proposed severity-triggered response, mapped to this platform's actual threat model

| Trigger | Immediate containment action (proposed) |
|---|---|
| VCN credential exfiltration suspected | Void all recently issued VCNs proactively; rotate the internal token used by the VCN-decrypt endpoint; review access logs for that endpoint |
| JWT signing key suspected compromised | Rotate the key immediately (this **requires** the rotation mechanism noted as missing in [`138-secrets-management.md`](138-secrets-management.md) — currently, this response step cannot actually be executed quickly) |
| Admin account suspected compromised | Force-revoke all sessions for that account; require password + MFA re-enrollment |
| Data breach (KYC/CNIC data exposed) | See [`../11-compliance/`](../11-compliance/) for legal notification obligations (flagged there as itself an undocumented gap) |

## The circular dependency worth flagging explicitly

The proposed response to a signing-key compromise depends on a rotation mechanism that doesn't exist yet (`INF-GAP-07`) — meaning the platform's *actual* current response to its most severe plausible security incident would be slower and more disruptive (likely requiring a full redeploy) than the response this document would otherwise recommend. **This is a strong argument for prioritizing secret rotation before this document's proposed playbook can be considered genuinely actionable**, not just theoretically correct.

## Related documents

[`../12-operations/41-incident-response-plan.md`](../12-operations/41-incident-response-plan.md), [`140-security-threat-model.md`](140-security-threat-model.md), [`138-secrets-management.md`](138-secrets-management.md).
