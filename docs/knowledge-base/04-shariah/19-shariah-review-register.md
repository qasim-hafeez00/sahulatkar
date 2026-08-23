# Shariah Decision & Review Register

> **STATUS: INTERNAL DRAFT — register not yet operational.** No Shariah Advisory Board decisions have been recorded as of this documentation pass; this document establishes the format and seeds it with the one confirmed open item found during codebase review. Populate this table going forward as real board decisions are made — do not treat the seed row as a completed review.

## Purpose

A permanent, append-only record of every Shariah Advisory Board decision affecting SahulatKar's product: what was asked, what was ruled, on what basis, and what implementation was required as a result. This is the audit trail that lets engineering, compliance, and any future regulator or Shariah reviewer trace *why* the product works the way it does.

## Format

| Field | Description |
|---|---|
| Decision ID | Sequential, e.g. `SDR-001` |
| Date | Date of board ruling |
| Question | What was asked of the board |
| Ruling | The board's decision |
| Evidence / basis | Shariah standard(s), scholarly reasoning cited |
| Advisor(s) | Which board member(s) issued the ruling |
| Affected product area | e.g. "Murabaha pricing," "Late fee mechanism" |
| Required implementation | What engineering/product must change as a result |
| Implementation status | Not started / In progress / Shipped / Verified |

## Register

| Decision ID | Date | Question | Ruling | Evidence | Advisor(s) | Affected area | Required implementation | Status |
|---|---|---|---|---|---|---|---|---|
| SDR-000 *(seed — not a real ruling)* | *Pending* | Is the tiered markup structure (2.5%/4.0%/7.0% by plan length: pay-in-3/4/6) Shariah-compliant as designed? | *Awaiting board review* | *Not yet submitted* | *Not yet assigned* | Murabaha pricing ([`../03-bnpl-financing/13-payment-plan-rules.md`](../03-bnpl-financing/13-payment-plan-rules.md)) | Board sign-off required before this pricing structure can be represented as Shariah-approved; code currently ships this structure with an unresolved `TODO` (`pricing_service.py:22`) | **Not started — this is the most urgent item to bring to the board**, since it is already implemented and offer-facing without approval |

## How to use this register going forward

1. Every proposed product/pricing/contract change that touches the Shariah structure gets a row **before** implementation, not after (see the process gap noted in [`18-shariah-governance.md`](18-shariah-governance.md)).
2. `Required implementation` should be specific enough that an engineer could pick it up without re-asking the board what was meant.
3. `Implementation status` should be kept current — this register is meant to be cross-checked against actual code state (e.g., via `docs/PRODUCTION_GAPS_REPORT.md`-style audits), not left as a static record of intent.
4. When a ruling is superseded by a later one, add the new row and mark the old ruling's status as `Superseded by SDR-0XX` rather than editing history out.

## Related documents

[`17-shariah-product-structure.md`](17-shariah-product-structure.md), [`18-shariah-governance.md`](18-shariah-governance.md).
