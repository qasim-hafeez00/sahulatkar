# Product Change Shariah Review

> **STATUS: INTERNAL DRAFT — policy statement, process not yet operational.**

## The rule

**Any change to the financing structure, fees, contract templates, or transaction flow must trigger a Shariah review before it ships to production.** This is the single governing principle this entire Shariah documentation folder is built around, and it is stated here explicitly as its own document because it's the rule most directly violated by the platform's one confirmed non-compliance incident (the tiered markup) — see [`85-shariah-non-compliance-handling.md`](85-shariah-non-compliance-handling.md).

## What counts as a triggering change

Per [`83-shariah-review-process.md`](83-shariah-review-process.md): markup/profit rate or fee-structure changes, contract template text changes, new financing products or plan types, changes to the late-fee/charity mechanism, changes to the prohibited-categories list's scope or basis.

## What does not require a fresh review

Purely technical refactors that don't change customer-facing terms (e.g., rewriting the pricing calculation code to fix a rounding bug, without changing the approved rate) — though even here, judgment is needed: a "just a rounding fix" that happens to change the effective total a customer pays by even a few rupees arguably does touch disclosed terms and should be treated conservatively (reviewed) rather than assumed exempt.

## How this should be enforced technically

Recommend a lightweight but real gate: a PR touching pricing/contract-template code paths should require a linked, resolved entry in [`19-shariah-review-register.md`](19-shariah-review-register.md) before merge — mirroring how the hard-gate CI test enforces the VCN-issuance rule. Today, nothing technical enforces this — it's a written policy only, which is exactly the condition under which the tiered-markup gap occurred.

## Related documents

[`83-shariah-review-process.md`](83-shariah-review-process.md), [`85-shariah-non-compliance-handling.md`](85-shariah-non-compliance-handling.md), [`19-shariah-review-register.md`](19-shariah-review-register.md).
