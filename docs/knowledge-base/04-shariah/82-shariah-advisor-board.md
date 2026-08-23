# Shariah Advisor / Board Documentation

> **STATUS: INTERNAL DRAFT.** No board members are named anywhere in current engineering documentation. This document records what's specified about board composition/budget (from [`18-shariah-governance.md`](18-shariah-governance.md)) and exists as the placeholder to be filled in once the board is actually constituted.

## What is specified

- Minimum composition: at least 1 SECP-recognized Shariah scholar.
- Budget: PKR 200,000–500,000 initial setup, PKR 100,000–200,000 annual audit.
- Cadence: quarterly audit, annual contract certification.
- Certification storage: `shariah_board_approvals` table (schema exists, currently empty).

## What is not specified — for Leadership to complete

- [ ] Named board member(s) and their credentials/SECP recognition status.
- [ ] Board size beyond the stated minimum of 1 (is a single scholar sufficient for a company at this scale, or is a multi-member board intended?).
- [ ] Appointment/term/succession process.
- [ ] Compensation structure and independence safeguards (relationship to company management, conflict-of-interest policy).
- [ ] Point of contact/process for engineering or product to submit a question to the board (currently, per [`18-shariah-governance.md`](18-shariah-governance.md), this process gap is evidenced by the tiered-markup change having shipped in code before board review).

## Why this matters beyond documentation completeness

A named, engaged Shariah board is the actual mechanism that resolves every open item flagged across this Shariah documentation folder — without it, [`17-shariah-product-structure.md`](17-shariah-product-structure.md)'s open questions and [`19-shariah-review-register.md`](19-shariah-review-register.md)'s seed entry have no path to resolution. This is arguably the single highest-leverage governance gap in the entire compliance/Shariah documentation set: everything else is waiting on this.

## Related documents

[`18-shariah-governance.md`](18-shariah-governance.md), [`19-shariah-review-register.md`](19-shariah-review-register.md), [`83-shariah-review-process.md`](83-shariah-review-process.md).
