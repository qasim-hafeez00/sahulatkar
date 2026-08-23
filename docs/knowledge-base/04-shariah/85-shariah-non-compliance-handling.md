# Shariah Non-Compliance Handling

> **STATUS: INTERNAL DRAFT — no non-compliance-handling process exists in current documentation.** This document proposes a starting structure, using the platform's own known non-compliance items as concrete grounding rather than a hypothetical.

## Why this needs to exist now, not hypothetically

The platform already has at least one live, confirmed non-compliance item: the tiered Murabaha markup shipped in code without Shariah board sign-off. This is not a hypothetical future scenario a policy needs to anticipate — it's a current fact the platform needs a process to handle, which is why this document leads with it rather than a generic framework.

## Proposed severity tiers

| Tier | Definition | Example |
|---|---|---|
| Tier 1 — Design pending approval | A feature is built per an engineering-understood design, but the design itself hasn't been board-reviewed yet | The tiered markup, today |
| Tier 2 — Confirmed deviation from an approved design | The board approved X, but the code does something materially different from X | Not currently known to exist, but the process should cover it |
| Tier 3 — Systemic enforcement failure | A rule the board explicitly required is enforced in policy but not in code, allowing it to be silently violated in production | The Wakalah-before-Murabaha ordering gap (`GW-BL-03`), or incomplete charity disbursement (`LS-CRIT-03`) |

## Proposed handling steps

1. **Identify and classify** the non-compliance against the tiers above.
2. **Contain** — for Tier 2/3, consider whether new instances of the non-compliant behavior should be paused (e.g., feature-flagged off) while resolution is pending, rather than continuing to accrue more affected transactions.
3. **Assess retroactive impact** — for transactions already affected (e.g., every Murabaha contract signed under the unapproved tiered markup), determine whether retroactive remediation is required (customer notification, fee adjustment, restated Shariah compliance report) — this is a decision for the board + Legal, not Engineering.
4. **Fix** — close the technical or process gap.
5. **Record** — log the incident and resolution in [`19-shariah-review-register.md`](19-shariah-review-register.md), regardless of tier, so the register reflects both approvals and non-compliance incidents.

## Immediate application to the known Tier 1 item

The tiered markup should be run through this process now: is it acceptable for new Murabaha contracts to continue being signed under the current (unapproved) rates while board review is pending, or should the platform revert to a single flat rate (the "4% flat" figure cited elsewhere in engineering docs) until the tiered structure is approved? **This is a decision Leadership/the Shariah board needs to make explicitly — this document does not make it for them.**

## Related documents

[`84-shariah-audit-process.md`](84-shariah-audit-process.md), [`19-shariah-review-register.md`](19-shariah-review-register.md), [`86-product-change-shariah-review.md`](86-product-change-shariah-review.md).
