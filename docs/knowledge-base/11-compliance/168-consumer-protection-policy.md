# Consumer Protection Policy

> **STATUS: INTERNAL DRAFT.** Complements [`38-responsible-financing-policy.md`](38-responsible-financing-policy.md) (which covers affordability/hardship specifically) with the broader consumer-protection lens: disclosure, fair treatment, and complaint handling.

## What's already strong, from a consumer-protection lens

Full upfront cost disclosure (enforced at the schema level, not just UX — see [`../04-shariah/17-shariah-product-structure.md`](../04-shariah/17-shariah-product-structure.md)), no hidden fees, and a fixed (non-escalating) installment schedule are all consumer-protection-favorable design choices, whether or not they were originally motivated by consumer-protection regulation specifically (they appear primarily Shariah-motivated, but happen to also serve this purpose well).

## Gaps specific to consumer protection (distinct from responsible-financing gaps already noted elsewhere)

- **No documented complaints/grievance procedure** — see [`170-complaints-grievance-procedure.md`](170-complaints-grievance-procedure.md).
- **No plain-language borrower disclosure summary** — the Murabaha contract carries full legal disclosure, but SECP's 2025 lending-framework amendments reportedly introduced a simplified "Borrower Factsheet" concept specifically because full contract language isn't sufficient for genuine consumer understanding (per general research in `docs/Sahulatkar-docs/`) — SahulatKar has no confirmed equivalent simplified summary screen, separate from the full contract, in its current design.
- **No documented cooling-off period** — many consumer-credit regulatory frameworks provide a short window after signing during which a customer can cancel without penalty; not referenced anywhere in current engineering docs, and directly relevant given the platform's own cancellation gap (customers currently can't cancel post-signing at all — see [`../02-business-workflows/09-refund-cancellation-workflow.md`](../02-business-workflows/09-refund-cancellation-workflow.md)).
- **No accessibility commitment** — not referenced (also noted in [`../09-qa/145-ui-testing-strategy.md`](../09-qa/145-ui-testing-strategy.md)).

## Recommended immediate action

The cooling-off period gap deserves particular attention: it intersects a genuine regulatory-consumer-protection question with an already-known engineering gap (no cancellation path post-signing), meaning fixing the engineering gap and defining the compliance policy should happen together, not sequentially.

## Related documents

[`38-responsible-financing-policy.md`](38-responsible-financing-policy.md), [`170-complaints-grievance-procedure.md`](170-complaints-grievance-procedure.md), [`../02-business-workflows/09-refund-cancellation-workflow.md`](../02-business-workflows/09-refund-cancellation-workflow.md).
