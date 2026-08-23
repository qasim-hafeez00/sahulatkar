# Shariah Compliance Requirements

> **STATUS: INTERNAL DRAFT.** A checklist of what the platform's own design claims it must satisfy to be Shariah-compliant — not a board-issued compliance standard. Use this as a pre-review checklist to hand the actual Shariah board, not as a substitute for their review.

## Mandatory technical requirements (already enforced at the code/schema level)

| Requirement | Enforcement mechanism | Verified how |
|---|---|---|
| Cost price disclosed before sale | `murabaha_contracts.cost_price NOT NULL` | Schema constraint — contract cannot be created without it |
| Profit amount disclosed before sale | `murabaha_contracts.profit_amount NOT NULL` | Schema constraint |
| Total repayable disclosed before sale | `murabaha_contracts.total_repayable NOT NULL` | Schema constraint |
| Prohibited goods excluded | `prohibited_categories` check before any offer | Application logic — **known gap: URL-based checking is incomplete (`PS-BL-01`)** |
| Late fees not retained as revenue | `fn_apply_late_fee()` trigger → `late_fee_charity_allocations` | DB trigger — **known gap: actual disbursement is a stub (`LS-CRIT-03`)** |
| Ownership transfer before resale | Wakalah signed before Murabaha can be generated | **Known gap: not actually enforced in code (`GW-BL-03`)** — a real compliance-relevant bug, not just a UX issue |

## Requirements that exist as policy statements but lack a corresponding technical or process enforcement

- Shariah board approval of any pricing/contract-structure change **before** it ships (the tiered markup was coded ahead of approval — see [`19-shariah-review-register.md`](19-shariah-review-register.md)).
- Late fee capped relative to principal (per Islamic finance principle) — `LS-BL-08` confirms this bound is not currently verified in code.
- Annual re-certification of contract templates tied to version bumps — the mechanism (`shariah_board_approvals` table) exists, but no certifications have actually been recorded.

## What "compliant" should mean before external claims are made

SahulatKar should not represent itself as "Shariah-certified" or "Shariah-compliant" in any external material until: (1) the board has reviewed and ruled on every open question in [`17-shariah-product-structure.md`](17-shariah-product-structure.md), (2) the enforcement gaps in the table above (Wakalah-before-Murabaha, charity disbursement, URL-based prohibited check) are closed in code, and (3) at least one certification is recorded in [`19-shariah-review-register.md`](19-shariah-review-register.md).

## Related documents

[`80-shariah-principles-constraints.md`](80-shariah-principles-constraints.md), [`17-shariah-product-structure.md`](17-shariah-product-structure.md), [`19-shariah-review-register.md`](19-shariah-review-register.md).
