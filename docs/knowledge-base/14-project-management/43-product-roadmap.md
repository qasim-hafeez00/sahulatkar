# Product Roadmap

**Status:** STABLE — sourced from `docs/MASTER_PLAN.md`. Note: this is a build-sequence roadmap (what order things get built in), not a market/GTM roadmap — no launch date, market-expansion, or GTM milestones are documented in current engineering docs.

## Phases

```
Phase 1 (Weeks 1–10)  — FOUNDATION: Auth, KYC, URL Pipeline, Credit Engine, Contracts
Phase 2 (Weeks 11–18) — CORE BUSINESS LOGIC: Payments, VCN, Checkout Agent, HITL
Phase 3 (Weeks 19–24) — SCALE: Delivery, Ledger, Admin Dashboard, Notifications
Phase 4 (Weeks 25–30) — PRODUCTION READINESS: Observability, Security hardening, Load testing, Launch
Phase 5 (unscheduled) — FUTURE GAPS & ENHANCEMENTS
```

## Phase 1 — Foundation (Sprints S01–S06)

Shared Python package hardening → Gateway auth → KYC/NADRA integration → Credit Engine completion → Shariah contracts → Product Service/URL pipeline. Per `docs/MASTER_PLAN.md`'s current-state table, this phase is largely built (marked "Done" for most components) — though "built" and "functionally complete" diverge in places per `docs/PRODUCTION_GAPS_REPORT.md` (e.g., Credit Engine is marked done but wasn't in scope of that audit; the URL pipeline has confirmed critical bugs despite being "done").

## Phase 2 — Core Business Logic (Sprints S07–S12)

Payment Orchestrator + VCN → Checkout Agent (Playwright automation) → HITL queue. This is where the platform's most severe current gap lives: the checkout agent's payment-form-filling logic is an incomplete stub (`PS-BL-03`), meaning this phase is not actually functionally complete despite being marked done in the build plan's component table.

## Phase 3 — Integrations & Scale (Sprints S13–S18)

Delivery tracking → Ledger & billing → Admin Dashboard (20 modules) → Notification Service → customer frontend. Frontend completion is the most visibly behind item here: `web-admin` is ~10% (shells, mock data) and `web-customer` is ~2% (scaffold only) per the last audit — i.e., customer-facing UI work is essentially still ahead, not behind schedule within a completed phase.

## Phase 4 — Production Readiness (Sprints S19–S22, not yet started per the audit)

Explicit checklist from `docs/MASTER_PLAN.md`: comprehensive E2E integration suite (full 12-step flow), chaos engineering (fault injection on Redis/DB/third-party timeouts), load testing (k6, 1,000 concurrent users), OWASP Top 10 security audit, penetration testing on payment/VCN flows, **SECP regulatory documentation**, **Shariah board contract certification**, data-residency verification, disaster-recovery runbook + simulation, on-call rotation and alerting framework. Given [`../10-devops/35-monitoring-logging.md`](../10-devops/35-monitoring-logging.md) confirms none of the observability stack is running yet, and [`../04-shariah/19-shariah-review-register.md`](../04-shariah/19-shariah-review-register.md) confirms no Shariah board decisions have been recorded, this phase has substantial work ahead regardless of how "done" earlier phases appear.

## Phase 5 — Future Gaps & Enhancements (explicitly forward-looking, unscheduled)

- Replace deterministic Playwright extractors with self-hosted LLM/VLM extraction entirely, for long-tail merchants.
- Cross-platform fraud-information-sharing capability with other Pakistani lenders.
- Slice `web-admin`'s 20 modules into micro-frontends if it outgrows a single Next.js app.
- Evolve AWS infrastructure from active-standby to multi-region active-active.

## Recommended sequencing correction (given the audit findings)

Because `docs/PRODUCTION_GAPS_REPORT.md` found Priority-1 (launch-blocking) bugs distributed across *all* of Phase 1–3's supposedly "done" components — not concentrated in Phase 4 as the phase structure might suggest — the practical near-term roadmap should probably be reframed as: **close the Priority 1 checklist in `docs/PRODUCTION_GAPS_REPORT.md` §13 first**, in roughly this order (highest-leverage first): fix the scraping-worker crash and prohibited-check gap (unblocks everything downstream) → complete the checkout form-filler (unblocks the core value proposition) → wire the `loan.created` event and GL-balance validation (unblocks financial integrity) → implement refunds → connect billing-sweep auto-collection. Only after those does Phase 4's observability/security/launch-readiness work become the correct next focus — building a production-readiness checklist on top of a platform that can't yet complete a purchase end-to-end would be sequencing backward.

## Related documents

[`44-architecture-decision-records.md`](44-architecture-decision-records.md), `docs/PRODUCTION_GAPS_REPORT.md` §13 (Master Gap Checklist), [`../01-company-product/02-product-vision.md`](../01-company-product/02-product-vision.md).
