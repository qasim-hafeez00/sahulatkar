# SahulatKar Knowledge Base

This is the consolidated internal documentation system for SahulatKar — the single place a developer, product manager, QA engineer, ops/support person, finance person, or new hire can go to understand what SahulatKar is, how it works, how money moves, and how every service fits together.

**Start here:** [`00-master-spec/MASTER_SPEC.md`](00-master-spec/MASTER_SPEC.md) — the single source of truth. Every other document goes deeper on one slice of it.

## How this knowledge base was built

Consolidated from three sources:
1. **`docs/System-md-files/`** and **`docs/MASTER_PLAN*.md`** — the existing engineering specs and build plan for this repo.
2. **`docs/PRODUCTION_GAPS_REPORT.md`** and **`docs/audits/`** — a code-verified audit of what's actually implemented vs. missing, dated 2026-04-27.
3. **`Desktop/bnpl/`** (mirrored at `docs/Sahulatkar-docs/`) — the original product research: KYC/fraud research, payment & delivery research, DB design volumes, UML diagrams, admin documentation.

Where source documents disagreed (see [`05-architecture/20-system-architecture.md`](05-architecture/20-system-architecture.md) for the `global_system_audit.md` vs. `PRODUCTION_GAPS_REPORT.md` discrepancy), this knowledge base defers to the line-by-line code audit (`PRODUCTION_GAPS_REPORT.md`) as ground truth and flags the gap explicitly rather than picking the more flattering number.

## Status legend

- **STABLE** — reflects the current codebase/design, verified against source.
- **INTERNAL DRAFT** — legal, regulatory, or Shariah content pending review by qualified counsel / the Shariah advisory board. Not for external distribution. See the banner at the top of each such document.
- **PLANNED** — describes target-state design for something not yet built; the doc says so explicitly.

## Index

### 00 — Master Spec
- [MASTER_SPEC.md](00-master-spec/MASTER_SPEC.md) — the one document that ties everything together

### 01 — Company & Product
- [01-product-overview.md](01-company-product/01-product-overview.md)
- [02-product-vision.md](01-company-product/02-product-vision.md)
- [03-business-model.md](01-company-product/03-business-model.md)
- [04-product-glossary.md](01-company-product/04-product-glossary.md)

### 02 — Business Workflows
- [05-customer-journey-e2e.md](02-business-workflows/05-customer-journey-e2e.md)
- [06-merchant-vendor-journey.md](02-business-workflows/06-merchant-vendor-journey.md)
- [07-bnpl-workflow-e2e.md](02-business-workflows/07-bnpl-workflow-e2e.md)
- [08-payment-workflow.md](02-business-workflows/08-payment-workflow.md)
- [09-refund-cancellation-workflow.md](02-business-workflows/09-refund-cancellation-workflow.md)
- [10-default-collections-workflow.md](02-business-workflows/10-default-collections-workflow.md)
- [11-merchant-settlement-reconciliation.md](02-business-workflows/11-merchant-settlement-reconciliation.md)

### 03 — BNPL & Financing
- [12-bnpl-product-specification.md](03-bnpl-financing/12-bnpl-product-specification.md)
- [13-payment-plan-rules.md](03-bnpl-financing/13-payment-plan-rules.md)
- [14-eligibility-rules.md](03-bnpl-financing/14-eligibility-rules.md)
- [15-credit-limit-rules.md](03-bnpl-financing/15-credit-limit-rules.md)
- [16-financing-state-machine.md](03-bnpl-financing/16-financing-state-machine.md)

### 04 — Shariah *(INTERNAL DRAFT — pending Shariah board review)*
- [17-shariah-product-structure.md](04-shariah/17-shariah-product-structure.md)
- [18-shariah-governance.md](04-shariah/18-shariah-governance.md)
- [19-shariah-review-register.md](04-shariah/19-shariah-review-register.md)

### 05 — Architecture
- [20-system-architecture.md](05-architecture/20-system-architecture.md)
- [21-service-responsibility-matrix.md](05-architecture/21-service-responsibility-matrix.md)
- [22-microservice-documentation.md](05-architecture/22-microservice-documentation.md) (index) → [microservices/](05-architecture/microservices/) (one file per service)

### 06 — API & Events
- [23-api-standards.md](06-api-events/23-api-standards.md)
- [24-event-catalog.md](06-api-events/24-event-catalog.md)

### 07 — Database
- [25-database-architecture.md](07-database/25-database-architecture.md)
- [26-database-dictionary.md](07-database/26-database-dictionary.md)

### 08 — Security
- [27-security-architecture.md](08-security/27-security-architecture.md)
- [28-kyc-verification-workflow.md](08-security/28-kyc-verification-workflow.md)
- [29-authentication-authorization.md](08-security/29-authentication-authorization.md)

### 09 — QA & Testing
- [30-qa-strategy.md](09-qa/30-qa-strategy.md)
- [31-test-case-repository.md](09-qa/31-test-case-repository.md)
- [32-financial-transaction-test-strategy.md](09-qa/32-financial-transaction-test-strategy.md)

### 10 — DevOps & Infrastructure
- [33-infrastructure-architecture.md](10-devops/33-infrastructure-architecture.md)
- [34-deployment-process.md](10-devops/34-deployment-process.md)
- [35-monitoring-logging.md](10-devops/35-monitoring-logging.md)

### 11 — Compliance & Regulatory *(INTERNAL DRAFT — pending legal review)*
- [36-compliance-requirements-matrix.md](11-compliance/36-compliance-requirements-matrix.md)
- [37-kyc-aml-policy.md](11-compliance/37-kyc-aml-policy.md)
- [38-responsible-financing-policy.md](11-compliance/38-responsible-financing-policy.md)

### 12 — Operations & Support
- [39-customer-support-sop.md](12-operations/39-customer-support-sop.md)
- [40-merchant-vendor-support-sop.md](12-operations/40-merchant-vendor-support-sop.md)
- [41-incident-response-plan.md](12-operations/41-incident-response-plan.md)

### 13 — Analytics
- [42-kpi-metrics-dictionary.md](13-analytics/42-kpi-metrics-dictionary.md)

### 14 — Project Management
- [43-product-roadmap.md](14-project-management/43-product-roadmap.md)
- [44-architecture-decision-records.md](14-project-management/44-architecture-decision-records.md)

## Scope note

This is the "mandatory" first-pass set (~44 documents + master spec) out of a much larger possible 23-category, ~200-document structure. The remaining categories (detailed per-table DB dictionary entries beyond the core schema, full SOP libraries, per-provider integration guides, ADR backfill for every historical decision, etc.) can be added incrementally — file names and numbering in this index leave room for that without renumbering existing docs.
