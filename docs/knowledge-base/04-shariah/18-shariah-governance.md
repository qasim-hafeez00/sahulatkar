# Shariah Governance Framework

> **STATUS: INTERNAL DRAFT.** This document summarizes what is *referenced* about Shariah governance in existing engineering specifications (`docs/System-md-files/M05-contracts.md`, `M11-ledger.md`) — it is not a governance charter and has not been reviewed or ratified by an actual Shariah Advisory Board, legal counsel, or company leadership. Where a field below says "not specified," that is a genuine gap to close, not an oversight in this document.

## What is specified in engineering docs today

- **Minimum board composition:** at least 1 SECP-recognized Shariah scholar (stated as a minimum, not a target board size).
- **Certification cadence:** annual review and certification of both contract templates (Wakalah, Murabaha).
- **Certification record-keeping:** stored in a `shariah_board_approvals` table.
- **Template versioning discipline:** any text change to a contract template requires a version bump and triggers a new certification requirement — i.e., certifications are tied to a specific template version, not a blanket approval.
- **Budget:** PKR 200,000–500,000 for initial setup; PKR 100,000–200,000 for annual audit (per `M05-contracts.md`).
- **Recurring audit cadence:** quarterly audit + annual contract certification (per the platform's regulatory reference table).
- **Compliance reporting mechanism:** `GET /admin/finance/shariah-report`, intended to surface Murabaha contract counts, average markup rate, ownership-transfer percentage, late fees collected, charity disbursed, and prohibited-items-blocked count for a given period. **Known gap:** the current Shariah audit endpoint (`admin_compliance.py — shariah_audit()`) only checks that `cost_price` is non-null; it does not verify that charity was actually disbursed or that the profit rate matches board-approved rates (`GW-BL-14`) — i.e., the reporting mechanism exists but does not yet do the checking a governance framework would require of it.

## What is not specified — open items for Legal/Leadership to define

- [ ] Formal board charter: appointment process, term length, replacement/succession, quorum, decision-making process (majority vote vs. unanimous, etc.).
- [ ] Board independence requirements (relationship to company management, compensation structure, conflict-of-interest policy).
- [ ] Escalation path when the board identifies a non-compliance issue post-launch (see [`../04-shariah/17-shariah-product-structure.md`](../04-shariah/17-shariah-product-structure.md) open questions for a live example — the tiered markup awaiting sign-off).
- [ ] Process for the board to review a *proposed* product change before implementation, vs. only certifying an already-built template (see below).
- [ ] Named board members and their credentials/regulator recognition (SECP-recognized scholar, specifically — not yet named in any document reviewed for this knowledge base).
- [ ] Relationship (if any) to the SECP's own Shariah governance framework/Shariah Governance Regulations for the entity's chosen licensing category.

## Product-change review requirement (design intent, process not yet formalized)

Engineering intent is clear on one governance principle: **any change to the financing structure, fees, contract templates, or transaction flow should trigger a Shariah review** before shipping — evidenced by the template-version-bump-triggers-recertification rule above, and the fact that the tiered markup change is explicitly blocked pending sign-off rather than shipped silently. What is not yet formalized is the *process*: who submits a change for review, what the SLA is, what happens if engineering ships ahead of a review (as appears to have already happened with the tiered markup being coded before approval — a process gap worth flagging to leadership directly).

## Related documents

[`17-shariah-product-structure.md`](17-shariah-product-structure.md), [`19-shariah-review-register.md`](19-shariah-review-register.md), [`../11-compliance/36-compliance-requirements-matrix.md`](../11-compliance/36-compliance-requirements-matrix.md).
