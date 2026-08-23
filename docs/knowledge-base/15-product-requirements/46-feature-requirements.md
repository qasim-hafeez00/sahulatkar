# Feature Requirements

**Status:** STABLE — one requirements summary per feature area, each linking to its full spec rather than duplicating it. This document exists so a reader can see the full feature list in one place before diving into any single area.

| Feature area | Core requirement | Full spec |
|---|---|---|
| Customer onboarding | Phone-verified registration in under a minute of user effort, no email required | [`../02-business-workflows/05-customer-journey-e2e.md`](../02-business-workflows/05-customer-journey-e2e.md) |
| KYC | Tier 1 auto-approval for the majority of clean applicants within 4 minutes; borderline cases routed to a 24-hr-SLA manual queue, not auto-rejected | [`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md) |
| URL-to-offer | Any pasted product URL resolves to a priced financing offer via a graceful 4-tier fallback, never a dead end for a valid product page | [`../05-architecture/microservices/product-service.md`](../05-architecture/microservices/product-service.md) |
| Credit decisioning | Sub-3-second decision using alternative data, functional for thin-file users with no bureau history | [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md) |
| Contract signing | Two-step OTP-signed contract flow that cannot be skipped or reordered, with full upfront cost disclosure | [`../04-shariah/17-shariah-product-structure.md`](../04-shariah/17-shariah-product-structure.md) |
| Payment collection | Multi-gateway down payment, biweekly automated installment collection with a defined retry cadence | [`../02-business-workflows/08-payment-workflow.md`](../02-business-workflows/08-payment-workflow.md) |
| Checkout automation | Autonomous purchase completion on arbitrary merchant sites, with human fallback inside a 15-minute SLA when automation fails | [`../05-architecture/microservices/product-service.md`](../05-architecture/microservices/product-service.md) |
| Delivery tracking | Real-time, multi-courier tracking visible to the customer, triggering the final installment activation on confirmed delivery | `docs/System-md-files/M10-M12-delivery-ledger-admin.md` (M10) |
| Collections | A defined, humane escalation timeline before any punitive action, with all late-fee revenue charity-routed | [`../02-business-workflows/10-default-collections-workflow.md`](../02-business-workflows/10-default-collections-workflow.md) |
| Admin operations | A single console covering users, orders, risk, finance, compliance, and support across 20 modules | `docs/System-md-files/M12-admin.md` |

## Cross-cutting requirements (apply to every feature above)

- Every financial amount must be `DECIMAL(14,2)`, never a float.
- Every state-changing financial action must be idempotent under retry.
- Every Shariah-relevant disclosure (cost price, profit, total repayable) must be enforced at the schema level, not just the UI.
- No feature may bypass the hard gate (VCN issuance requires signed Murabaha) under any code path.

## Related documents

[`45-prd.md`](45-prd.md), [`47-user-stories.md`](47-user-stories.md), [`48-acceptance-criteria.md`](48-acceptance-criteria.md).
