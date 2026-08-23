# Product Mission

**Status:** STABLE — synthesized from the consistent framing across all engineering source documents (`docs/System-md-files/00Sahulatkar-System.md`, `docs/MASTER_PLAN.md`, `docs/audits/global_system_audit.md`), which all open with the same one-line description.

## Mission

To let any Pakistani consumer buy anything sold online, from any store, and pay for it over time — without interest, without needing that store to have partnered with a BNPL provider, and without needing a pre-existing credit history.

## Restated as a single sentence (the line every source document leads with)

> "Pakistan's first vendor-agnostic, Shariah-compliant BNPL platform: paste any product URL, an AI agent buys it, repay in installments under a Murabaha contract."

## Why this is a mission statement and not just a product description

Three commitments are baked into that one sentence, each of which constrains what SahulatKar will and won't do as it grows:

1. **"Any product URL"** — a commitment to universal coverage over curated merchant partnerships, even where partnerships would be operationally easier (see [`../02-business-workflows/06-merchant-vendor-journey.md`](../02-business-workflows/06-merchant-vendor-journey.md) for what this costs operationally).
2. **"Shariah-compliant"** — a commitment to a specific financing structure (Agency Murabaha, not interest), not just a "we also offer an Islamic option" add-on. This shapes the core contract flow (Wakalah before Murabaha), not a variant of it — see [`../04-shariah/17-shariah-product-structure.md`](../04-shariah/17-shariah-product-structure.md).
3. **"An AI agent buys it"** — a commitment to automation as the delivery mechanism, not merely as a cost optimization. The product's value proposition (buy from anywhere) is only deliverable at scale if the checkout agent actually works — which is why its current incompleteness (see [`../05-architecture/microservices/product-service.md`](../05-architecture/microservices/product-service.md)) is a mission-level risk, not just an engineering backlog item.

## Related documents

[`01-product-overview.md`](01-product-overview.md), [`02-product-vision.md`](02-product-vision.md), [`03-business-model.md`](03-business-model.md).
