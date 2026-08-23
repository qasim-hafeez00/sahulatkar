# Product Requirements Document (PRD) — SahulatKar Platform

**Status:** STABLE — assembled from the build plan and module specs (`docs/MASTER_PLAN.md`, `docs/System-md-files/M01`–`M12`), which collectively function as the platform's PRD even though no single document was previously labeled as one. This document is the index/summary; each linked module doc carries the actual requirement detail.

## Purpose of this document

A single place that states, for the whole platform, what must be true for each major capability to be considered done — pointing to the authoritative detail rather than duplicating it, since that detail already exists in well-maintained module specs.

## In scope

| Capability | Requirement summary | Detail |
|---|---|---|
| Registration & Auth | Phone-OTP registration, JWT session management, admin MFA | [`../08-security/29-authentication-authorization.md`](../08-security/29-authentication-authorization.md) |
| KYC | CNIC OCR + NADRA + liveness + face match, <4 min Tier 1 target | [`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md) |
| URL extraction | Any product URL → structured, priced offer via a 4-tier waterfall | [`../02-business-workflows/07-bnpl-workflow-e2e.md`](../02-business-workflows/07-bnpl-workflow-e2e.md), [`../05-architecture/microservices/product-service.md`](../05-architecture/microservices/product-service.md) |
| Credit decisioning | 7-layer pipeline, <3s SLA, band-based limit/down-payment | [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md) |
| Shariah contracts | Wakalah then Murabaha, OTP-signed, hard-gated | [`../04-shariah/17-shariah-product-structure.md`](../04-shariah/17-shariah-product-structure.md) |
| Payments | Down payment + installment collection across 3 gateways | [`../02-business-workflows/08-payment-workflow.md`](../02-business-workflows/08-payment-workflow.md) |
| VCN & checkout automation | Single-use card, autonomous purchase execution, HITL fallback | [`../05-architecture/microservices/payment-orchestrator.md`](../05-architecture/microservices/payment-orchestrator.md), [`../05-architecture/microservices/product-service.md`](../05-architecture/microservices/product-service.md) |
| Delivery tracking | Multi-courier tracking via AfterShip | [`../05-architecture/microservices/notification-service.md`](../05-architecture/microservices/notification-service.md) |
| Ledger & collections | Double-entry bookkeeping, daily billing sweep, charity routing | [`../20-ledger-accounting/`](../20-ledger-accounting/) |
| Admin dashboard | 20-module operations/risk/finance/compliance console | `docs/System-md-files/M12-admin.md` |

## Out of scope (explicitly, given the product's own design)

- Merchant onboarding, merchant checkout SDK/API, merchant-side integration of any kind — see [`../02-business-workflows/06-merchant-vendor-journey.md`](../02-business-workflows/06-merchant-vendor-journey.md).
- Revolving credit lines, multi-item basket financing, cash-out products — the financing model is strictly one-order-one-loan (see [`../03-bnpl-financing/12-bnpl-product-specification.md`](../03-bnpl-financing/12-bnpl-product-specification.md)).
- Markets outside Pakistan (see [`../01-company-product/02-product-vision.md`](../01-company-product/02-product-vision.md)).

## Non-functional requirements (as documented)

Credit decision SLA <3 seconds p99; KYC Tier 1 target <4 minutes; ≥80% unit test coverage on changed code; all monetary values `DECIMAL(14,2)`; data residency confined to AWS `ap-south-1`; ≥80% end-to-end purchase automation target (stated in the platform quick-reference as a goal — **not yet met**, since checkout completion is currently an incomplete stub per [`../05-architecture/microservices/product-service.md`](../05-architecture/microservices/product-service.md)).

## How requirements and reality currently diverge

This PRD describes target requirements. `docs/PRODUCTION_GAPS_REPORT.md` is the authoritative record of which requirements are actually met today (~55% platform completion) — every linked detail document above states its own gaps explicitly rather than this index re-deriving them.

## Related documents

[`46-feature-requirements.md`](46-feature-requirements.md), [`47-user-stories.md`](47-user-stories.md), [`48-acceptance-criteria.md`](48-acceptance-criteria.md), [`../14-project-management/43-product-roadmap.md`](../14-project-management/43-product-roadmap.md).
