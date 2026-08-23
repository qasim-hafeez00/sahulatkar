# Shariah Audit Process

> **STATUS: INTERNAL DRAFT.** Distinct from [`83-shariah-review-process.md`](83-shariah-review-process.md) (reviewing a *proposed change* before it ships) — this document covers *auditing what's already live* on a recurring cadence.

## Specified cadence

Quarterly audit (per [`18-shariah-governance.md`](18-shariah-governance.md)), annual full contract-template re-certification.

## What an audit should check (proposed, based on what the reporting endpoint is designed to surface)

`GET /admin/finance/shariah-report` is designed to return, per period: Murabaha contract count, average markup rate, ownership-transfer percentage, late fees collected, charity disbursed, and prohibited-items-blocked count (see `docs/System-md-files/M10-M12-delivery-ledger-admin.md`, M11 section). A quarterly audit should verify each of these against actual ledger/transaction data, not just that the report renders.

## Known gap that directly undermines this process today

The current Shariah audit *endpoint logic* (`admin_compliance.py — shariah_audit()`) only checks that `cost_price` is non-null on Murabaha contracts — it does **not** verify that charity was actually disbursed, or that the profit rate charged matches board-approved rates (`GW-BL-14`). This means even if the quarterly audit cadence were happening today, the tooling meant to support it would give a false sense of assurance — passing this check confirms disclosure happened, not that the late-fee-charity promise or the pricing-approval requirement were actually honored.

## Proposed audit checklist (until the above gap is closed, this checklist should be run manually)

- [ ] For a sample of Murabaha contracts this period: cost price, profit, and total repayable are present and internally consistent (profit = cost × approved rate).
- [ ] For every late fee collected this period: a corresponding `late_fee_charity_allocations` record exists with a `disbursed_at` timestamp — not just `allocated_at`.
- [ ] For every prohibited-category block logged: confirm it correctly matched an actually-prohibited product (spot-check for false positives/negatives).
- [ ] Profit rates charged match the currently board-approved rate(s) — cross-reference [`19-shariah-review-register.md`](19-shariah-review-register.md).

## Related documents

[`83-shariah-review-process.md`](83-shariah-review-process.md), [`85-shariah-non-compliance-handling.md`](85-shariah-non-compliance-handling.md), [`../11-compliance/36-compliance-requirements-matrix.md`](../11-compliance/36-compliance-requirements-matrix.md).
