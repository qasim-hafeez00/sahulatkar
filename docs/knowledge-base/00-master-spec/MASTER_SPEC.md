# SahulatKar — Master Product & System Specification

**Status:** STABLE (architecture/product sections) · INTERNAL DRAFT (Shariah/compliance sections — see banners below)
**Last verified against source:** 2026-08-22, using `docs/MASTER_PLAN.md`, `docs/System-md-files/*`, `docs/PRODUCTION_GAPS_REPORT.md` (2026-04-27), `docs/audits/global_system_audit.md`.

This is the central source of truth for SahulatKar. Every other document in `docs/knowledge-base/` goes deeper on one section of this one. If something here and a detailed doc disagree, the detailed doc is more current on its topic — but file it as a doc-sync bug.

---

## 1. Executive Summary

SahulatKar is Pakistan's first **vendor-agnostic, Shariah-structured Buy-Now-Pay-Later (BNPL) platform**. A user pastes the URL of *any* product from *any* online store; an AI agent buys it on their behalf; the user repays SahulatKar in installments under an Islamic Murabaha (cost-plus-sale) contract, preceded by a Wakalah (agency) agreement authorizing the purchase.

This is fundamentally different from merchant-network BNPL (Klarna, Affirm, Tabby): SahulatKar does not integrate with merchants or require them to accept anything. It acts as a **purchasing agent and financier in one**, buying like an ordinary retail customer using a single-use virtual card, then re-selling the item to the customer at cost plus a disclosed markup, repaid over time.

## 2. What is SahulatKar?

- A Next.js customer app where a user pastes a product URL from anywhere on the internet.
- A backend pipeline that scrapes/extracts the product, prices it, runs a sub-3-second credit decision, and presents a financing offer.
- Two Shariah contracts (Wakalah, then Murabaha) the user signs via OTP before any money moves.
- A down payment (25–40%) collected up front, followed by issuance of a single-use, MCC-locked virtual card (VCN).
- A Playwright-based autonomous browser agent that completes checkout on the merchant's actual website using that VCN, with a human-in-the-loop (HITL) fallback for anything automation can't handle.
- Delivery tracking, then biweekly installment collection until the loan is repaid.

Full narrative: [01-company-product/01-product-overview.md](../01-company-product/01-product-overview.md).

## 3. Problem Statement

Traditional BNPL requires the merchant to integrate with the BNPL provider — so coverage is limited to whichever stores signed up. Most of what a Pakistani consumer wants to buy (global e-commerce, small independent stores, marketplaces without local integrations) is invisible to merchant-network BNPL. Separately, most Pakistani consumers are "thin-file" — no traditional credit bureau history — which locks them out of conventional financing, and observant Muslim consumers additionally need the credit product itself to be interest-free and Shariah-structured.

SahulatKar addresses both: universal merchant coverage (buy from anywhere, no merchant integration needed) and a cost-plus-sale (Murabaha) structure instead of interest, using alternative data (device, behavioral, telco signals) for underwriting instead of requiring existing bureau history.

## 4. Target Users

Primary: Pakistani consumers who want to buy a specific product (electronics, apparel, appliances) they've found online but can't pay the full price today, including thin-file/no-bureau-history users. Age 18+ (hard-blocked below), phone-first (E.164 `+92` numbers), CNIC-verified.

Not covered by this platform: merchants seeking a checkout/financing integration (there is no such integration surface — see [02-business-workflows/06-merchant-vendor-journey.md](../02-business-workflows/06-merchant-vendor-journey.md)).

## 5. Product Ecosystem

| Surface | Purpose |
|---|---|
| `apps/web-customer` (Next.js) | Customer-facing app: URL paste → offer → contracts → payment → tracking |
| `apps/web-admin` (Next.js) | 20-module admin dashboard: ops, risk, finance, compliance, support |
| `apps/gateway` | BFF: auth, KYC orchestration, RBAC, hard gates, contracts, routing |
| `apps/product-service` | URL extraction waterfall, Universal Product Object (UPO), checkout agent |
| `apps/credit-engine` | 7-layer real-time credit/fraud scoring |
| `apps/payment-orchestrator` | VCN lifecycle, down payment + installment collection, gateway reconciliation |
| `apps/ledger-service` | Double-entry bookkeeping, billing sweep, charity routing, financial reports |
| `apps/notification-service` | SMS/WhatsApp/push/email, delivery tracking webhooks |

## 6. Business Model

Revenue: a disclosed Murabaha profit margin (markup) on the cost of the product, tiered by repayment plan length (2.5% / 4.0% / 7.0% for pay-in-3/4/6 as currently coded — **not yet Shariah-board approved, see §11**), plus payment-interchange-like economics. Costs: payment gateway fees, VCN issuance, third-party extraction/OCR/LLM API costs, SMS/logistics, and expected credit losses. Full breakdown, unit economics, and the compliance caveat on tiered pricing: [01-company-product/03-business-model.md](../01-company-product/03-business-model.md).

## 7. Customer Journey

Registration (phone OTP) → KYC (CNIC OCR + NADRA + liveness + face match) → paste a product URL → AI extraction → credit decision (<3s) → offer → sign Wakalah → sign Murabaha (hard gate) → pay down payment → VCN issued → AI agent completes checkout → delivery tracked → biweekly installments until paid off. Full detail: [02-business-workflows/05-customer-journey-e2e.md](../02-business-workflows/05-customer-journey-e2e.md).

## 8. Merchant / Vendor Journey

There is no merchant onboarding pipeline. "Merchants" are arbitrary third-party websites SahulatKar's checkout agent transacts with as an ordinary retail customer. A subset are recognized/optimized "affiliate partners" (Rye-API-supported Shopify/Amazon-class stores) with a `commission_rate` and tracked `checkout_success_rate`, but none of this requires the merchant's awareness or participation. Detail and the operational implications of this model (returns, bans, disputes): [02-business-workflows/06-merchant-vendor-journey.md](../02-business-workflows/06-merchant-vendor-journey.md).

## 9. Complete BNPL Lifecycle (the 12-Step Order Flow — immutable sequence)

```
 1. User pastes product URL                     → Gateway → Product Service
 2. Playwright + BrightData scrapes merchant page
 3. GPT-4o Vision extracts Universal Product Object (UPO)
 4. XGBoost 7-layer credit assessment            < 3 seconds
 5. Financing offer presented: cost + markup, fully disclosed
 6. User signs Wakalah Agreement via OTP
 7. User signs Murabaha Contract via OTP          ← HARD GATE
 8. Down payment collected (25–40%)               via Safepay / JazzCash / Raast
 9. Single-use VCN issued (MCC-locked, amount-capped) ← blocked until step 7
10. Playwright agent completes checkout at merchant
11. Delivery tracked via AfterShip
12. Remaining installments auto-collected biweekly
```

**HARD GATE RULE:** VCN issuance (step 9) cannot execute until the Murabaha contract is signed (step 7). Gateway middleware enforces this with HTTP 403 `MURABAHA_NOT_SIGNED`; the corresponding CI test must never be skipped or marked `xfail`. Full lifecycle detail: [02-business-workflows/07-bnpl-workflow-e2e.md](../02-business-workflows/07-bnpl-workflow-e2e.md) and state machine: [03-bnpl-financing/16-financing-state-machine.md](../03-bnpl-financing/16-financing-state-machine.md).

## 10. Financing Model

Cost price + shipping = base. Profit (markup) applied per plan: 2.5% (pay-in-3), 4.0% (pay-in-4), 7.0% (pay-in-6). Down payment 25–40% depending on credit band, collected before VCN issuance. Remainder split into equal installments (last one rounding-adjusted), collected biweekly. Late fees are calculated but **100% routed to charity (Edhi Foundation)** — SahulatKar retains zero late-fee revenue by design. Detail: [03-bnpl-financing/12-bnpl-product-specification.md](../03-bnpl-financing/12-bnpl-product-specification.md), [13-payment-plan-rules.md](../03-bnpl-financing/13-payment-plan-rules.md).

## 11. Shariah Structure — INTERNAL DRAFT, PENDING SHARIAH BOARD REVIEW

> **STATUS: INTERNAL DRAFT.** Not reviewed by a qualified Shariah advisory board. Not a fatwa or compliance certification. Do not represent this platform as "Shariah-certified" externally until §17–19 are formally reviewed and signed off.

The product is structured as an **Agency Murabaha**: the customer first appoints SahulatKar as *Wakeel* (agent) to purchase a specific product at an authorized amount (Wakalah Agreement); SahulatKar then sells the procured product to the customer at cost plus a disclosed, fixed profit margin (Murabaha Contract), with a fixed installment schedule that cannot change after signing. Three rules are enforced at the database level: (1) late fees are 100% charity-routed, zero retained by the platform; (2) cost price, profit amount, and profit rate are all `NOT NULL` on the Murabaha contract record — a contract literally cannot be generated without full disclosure; (3) prohibited-category products (alcohol, tobacco, gambling, adult content, weapons, interest-bearing instruments) are blocked before any offer is shown. Known open compliance item: the tiered markup-by-plan-length structure has **not yet received written Shariah board sign-off** (`pricing_service.py:22` TODO, confirmed in the 2026-04-27 code audit) — this is a launch blocker, not a documentation gap. Full detail: [04-shariah/17-shariah-product-structure.md](../04-shariah/17-shariah-product-structure.md).

## 12. Credit & Risk

A 7-layer real-time pipeline (hard blocks → velocity/fraud → identity/device score → alternative data → ML scoring (XGBoost/LightGBM ensemble) → order-category overlay → portfolio concentration controls), total SLA under 3 seconds. Outputs one of five credit bands (A–F) with an associated limit and down-payment percentage. Full detail: [03-bnpl-financing/14-eligibility-rules.md](../03-bnpl-financing/14-eligibility-rules.md), [15-credit-limit-rules.md](../03-bnpl-financing/15-credit-limit-rules.md).

## 13. Payment Architecture

"Collect first, then buy": down payment must clear before a VCN is ever issued, and a VCN is never issued before the Murabaha is signed. Payment methods, in priority order: Safepay (cards/wallets), JazzCash Direct API, EasyPaisa Direct API, Raast (SBP instant rail, Phase 4/not yet live). Detail: [02-business-workflows/08-payment-workflow.md](../02-business-workflows/08-payment-workflow.md).

## 14. Ledger & Accounting

Double-entry bookkeeping (`journal_entries` / `journal_entry_lines`, debit = credit enforced — **though the 2026-04-27 audit found this invariant is not actually validated in code today, see §20 gaps**), a daily billing sweep over a partial index on `installments(due_date, user_id) WHERE status='pending'`, and dedicated charity-routing tables for late fees. Detail: [07-database/25-database-architecture.md](../07-database/25-database-architecture.md).

## 15. Merchant Settlement

There is no merchant settlement in the traditional BNPL sense (SahulatKar doesn't pay merchants directly on the customer's behalf via an integration — it pays them exactly as a retail customer would, via the VCN, at time of checkout). What *is* reconciled is SahulatKar's own payment-gateway settlement (Safepay/JazzCash inbound collections vs. what actually lands in SahulatKar's bank account) — as of the last code audit this reconciliation runs against mock local files, not live gateway APIs. Detail: [02-business-workflows/11-merchant-settlement-reconciliation.md](../02-business-workflows/11-merchant-settlement-reconciliation.md).

## 16. Refunds & Disputes

Refund pathway exists as an API stub only (`RefundOrchestrator.initiate_refund()` unimplemented as of the last audit) — this is a Priority-1 launch blocker, not a design gap. Detail and target design: [02-business-workflows/09-refund-cancellation-workflow.md](../02-business-workflows/09-refund-cancellation-workflow.md).

## 17. Microservice Architecture

6 FastAPI microservices + 2 Next.js frontends, PostgreSQL 16 as system of record (169 tables across 13 domains per the design spec), Redis for cache/pub-sub/queues, deployed to AWS EKS in `ap-south-1` (Pakistan-adjacent, for data residency). Full detail: [05-architecture/20-system-architecture.md](../05-architecture/20-system-architecture.md), [21-service-responsibility-matrix.md](../05-architecture/21-service-responsibility-matrix.md).

## 18. APIs

REST, versioned under `/api/v1` / `/v1`, JWT bearer auth (RS256), internal service-to-service calls authenticated via a shared `X-Internal-Token` HMAC. Standards: [06-api-events/23-api-standards.md](../06-api-events/23-api-standards.md).

## 19. Database

PostgreSQL 16, all monetary fields `DECIMAL(14,2)` (never float), dual PK strategy (`BIGSERIAL` internal + `UUID` external), soft deletes, `pgcrypto` AES-256 for CNIC/IBAN/VCN, quarterly/monthly partitioning on high-volume tables. Detail: [07-database/25-database-architecture.md](../07-database/25-database-architecture.md), [26-database-dictionary.md](../07-database/26-database-dictionary.md).

## 20. Events

Redis Pub/Sub event bus connects services (e.g. `payment.down_payment_confirmed` → VCN issuance; `order.purchase_confirmed` → delivery tracking). One event the audit confirms is **structurally missing** end-to-end: nothing publishes `loan.created` when a Murabaha is signed, so the Ledger Service never posts the initial liability/receivable entries for any loan — this is the single highest-severity cross-service gap in the platform today. Full catalog: [06-api-events/24-event-catalog.md](../06-api-events/24-event-catalog.md).

## 21. Security

RS256 JWT (15-min access / 24-hr refresh), mandatory TOTP MFA for all admin accounts, RBAC with 8 defined roles, PII encrypted at rest, VCN PAN/CVV encrypted and never logged, data residency committed to AWS `ap-south-1`. Detail: [08-security/27-security-architecture.md](../08-security/27-security-architecture.md).

## 22. Compliance — INTERNAL DRAFT, PENDING LEGAL REVIEW

> **STATUS: INTERNAL DRAFT.** This section and its linked documents summarize *applicable regulatory bodies and known obligations* as understood from internal engineering docs. They are not a legal opinion, not a licensing filing, and have not been reviewed by qualified counsel. SahulatKar's actual license/registration status with SECP is not recorded anywhere in this repository as of this writing — treat as unconfirmed.

Regulators/obligations referenced in the engineering docs: SECP (NBFC license or Regulatory Sandbox; Islamic Finance Guidelines 2023), SBP (monthly RCD-1 reporting, AML/CFT), FMU (Suspicious Transaction Reports within 7 days, automatic Currency Transaction Report detection), NADRA (CNIC verification backbone), TASDEEQ (mandatory credit bureau reporting), PECA 2016 (Pakistan data residency, OTP-based e-signatures), and a Shariah Board (quarterly audit, annual contract certification). Full detail and open questions: [11-compliance/36-compliance-requirements-matrix.md](../11-compliance/36-compliance-requirements-matrix.md).

## 23. Customer Support

HITL queue (15-minute SLA) for anything the checkout agent can't finish automatically; a separate KYC manual-review queue (24-hour SLA) for borderline identity verification; admin support ticketing is speced (AD-14/AD-15) but not yet built as of the last audit. Detail: [12-operations/39-customer-support-sop.md](../12-operations/39-customer-support-sop.md).

## 24. Analytics

Executive KPIs: GMV, approval rate, default rate, collection rate, fraud loss rate, NPS, cohort retention/LTV — with traffic-light thresholds already defined for the admin dashboard (e.g. default rate green <1.5%, red >2.5%). Full dictionary: [13-analytics/42-kpi-metrics-dictionary.md](../13-analytics/42-kpi-metrics-dictionary.md).

## 25. Failure Scenarios (Current, Known)

The 2026-04-27 code audit (`docs/PRODUCTION_GAPS_REPORT.md`) is the canonical source for this. Highlights, because they materially affect what "SahulatKar" means operationally today vs. on paper:

- **Overall platform completion estimate: ~55%.** Backend services range 60–85% complete; `web-customer` is ~2% (scaffold only); `web-admin` is ~10% (shells with mock data).
- **14 launch-blocking (Priority 1) gaps**, including: the scraping worker crashes on every job (undefined variable, `scraping_worker.py:117`); the Playwright checkout form-filler that actually enters VCN payment details is an unfinished stub, so no automated purchase can complete end-to-end; refunds have no implementation; general-ledger entries are posted without validating debits = credits; nothing triggers automatic installment collection on the due date; credit reservation at order time doesn't decrement available credit, so concurrent orders can double-spend a user's limit.
- Full checklist, organized by priority: [PRODUCTION_GAPS_REPORT.md](../../PRODUCTION_GAPS_REPORT.md) (kept in place rather than duplicated here — it's a living audit, not static product spec).

Every architecture/workflow document in this knowledge base describes the **target design**; where the current code deviates materially, that document says so explicitly and links back to the relevant gap ID(s) above.

## 26. Future Roadmap

See [14-project-management/43-product-roadmap.md](../14-project-management/43-product-roadmap.md) for the phase-by-phase build plan (Foundation → Core Business Logic → Integrations & Scale → Production Readiness) and the Phase 5 forward-looking items (dynamic extraction failover, cross-platform fraud sharing, multi-region resiliency).

## 27. Glossary

See [01-company-product/04-product-glossary.md](../01-company-product/04-product-glossary.md).

## 28. Related Documents

Full index: [`../README.md`](../README.md).
