# Product Vision

**Status:** STABLE (near-term, derived from `docs/MASTER_PLAN.md` phasing and the credit-engine design) · PLANNED (long-term extrapolation, flagged where speculative)

## Where SahulatKar is going

The build plan (`docs/MASTER_PLAN.md`) is organized in four phases plus a forward-looking fifth:

1. **Foundation** — auth, KYC, URL pipeline, credit engine, Shariah contracts.
2. **Core Business Logic** — payments, VCN issuance, the autonomous checkout agent, human-in-the-loop fallback.
3. **Integrations & Scale** — delivery tracking, ledger/billing, the full admin dashboard, notification channels.
4. **Production Readiness** — observability, security hardening, load testing, launch.
5. **Future Gaps & Enhancements** (explicitly forward-looking in the source plan):
   - Replace deterministic Playwright extractors with self-hosted LLM/VLM extraction entirely, for long-tail merchants with no working parser.
   - Build modular cross-platform fraud-information-sharing capability with other Pakistani lenders/BNPL providers.
   - Slice the 20-module `web-admin` into micro-frontends if it outgrows a single Next.js app.
   - Evolve AWS infrastructure from active-standby to multi-region active-active as transaction volume outgrows single-region (`ap-south-1`) capacity.

Sprint-by-sprint detail: [`../14-project-management/43-product-roadmap.md`](../14-project-management/43-product-roadmap.md).

## 5-year vision *(PLANNED — directional, not a committed roadmap)*

The architecture is deliberately built to generalize past a single financing product:

- **Credit Engine as a reusable underwriting core.** The 7-layer pipeline (hard blocks → velocity → identity/device → alternative data → ML scoring → category overlay → portfolio controls) is architected as its own service with its own APIs, independent of the URL-purchase flow — a natural base for additional financing products beyond single-item BNPL (e.g., a revolving limit, or financing initiated from something other than a pasted URL).
- **Ledger Service as the system of financial record.** Double-entry bookkeeping with a defined chart of accounts positions the platform to support new transaction types (additional fee types, new financing products, marketplace-style flows) without re-architecting the accounting layer.
- **Vendor-agnostic extraction as a standalone capability.** The URL → Universal Product Object pipeline (extraction waterfall + UPO schema) is generically useful beyond BNPL — e.g., price-tracking, universal cart/wishlist features, or third-party product-data APIs — though none of this is committed roadmap today.

## Target market

Pakistani consumers today, phone-first (E.164 `+92`), with a working legal CNIC, transacting in PKR. The credit engine's cross-border risk overlay (Layer 6, in [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md)) is specifically tuned for Pakistan-specific fraud patterns (freight-forwarder addresses, airport-adjacent delivery, peak migration-month behavior), which signals the near-term market is Pakistan-only rather than a generic emerging-market play.

## Product evolution

The near-term product surface is fixed by the 12-step order flow (see [`MASTER_SPEC.md` §9](../00-master-spec/MASTER_SPEC.md#9-complete-bnpl-lifecycle-the-12-step-order-flow--immutable-sequence)) — described as an "immutable sequence" in the engineering docs, meaning changes to *that* flow are treated as a significant, deliberate design decision rather than routine iteration. Evolution in the near term is expected within phases (adding payment rails like Raast, adding admin modules, hardening the checkout agent's failure handling) rather than changing the core mechanic.

## Future products *(PLANNED — not committed)*

Not specified in current engineering documentation beyond the Phase 5 items above. Any expansion into new financing products, new markets, or new customer segments should be captured here once decided — this section exists as the placeholder for that decision, not as a prediction of it.
