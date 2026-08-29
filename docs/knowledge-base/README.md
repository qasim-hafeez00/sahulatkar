# SahulatKar Knowledge Base

This is the consolidated internal documentation system for SahulatKar — the single place a developer, product manager, QA engineer, ops/support person, finance person, or new hire can go to understand what SahulatKar is, how it works, how money moves, and how every service fits together.

**Start here:** [`00-master-spec/MASTER_SPEC.md`](00-master-spec/MASTER_SPEC.md) — the single source of truth. Every other document goes deeper on one slice of it.

213 documents across 23 categories.

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

## Two things worth knowing before you read anything else

1. **SahulatKar is vendor-agnostic — it has no merchants in the normal BNPL sense.** It buys from any URL as an ordinary retail customer, with no merchant onboarding, integration, or account. Every "Merchant" document in this knowledge base explains what actually happens instead. Start with [`02-business-workflows/06-merchant-vendor-journey.md`](02-business-workflows/06-merchant-vendor-journey.md).
2. **The platform is ~55% functionally complete**, per a 2026-04-27 line-by-line code audit (`docs/PRODUCTION_GAPS_REPORT.md`), despite most components being architecturally "done." Every document here describes the *target design*; where current code deviates materially, the document says so explicitly with a gap ID you can trace back to that audit.

## Index

### 00 — Master Spec
- [MASTER_SPEC.md](00-master-spec/MASTER_SPEC.md) — the one document that ties everything together

### 01 — Company & Product
- [01-product-overview.md](01-company-product/01-product-overview.md)
- [02-product-vision.md](01-company-product/02-product-vision.md)
- [03-business-model.md](01-company-product/03-business-model.md)
- [04-product-glossary.md](01-company-product/04-product-glossary.md)
- [05-product-mission.md](01-company-product/05-product-mission.md)

### 02 — Business Workflows
- [05-customer-journey-e2e.md](02-business-workflows/05-customer-journey-e2e.md)
- [06-merchant-vendor-journey.md](02-business-workflows/06-merchant-vendor-journey.md)
- [07-bnpl-workflow-e2e.md](02-business-workflows/07-bnpl-workflow-e2e.md)
- [08-payment-workflow.md](02-business-workflows/08-payment-workflow.md)
- [09-refund-cancellation-workflow.md](02-business-workflows/09-refund-cancellation-workflow.md)
- [10-default-collections-workflow.md](02-business-workflows/10-default-collections-workflow.md)
- [11-merchant-settlement-reconciliation.md](02-business-workflows/11-merchant-settlement-reconciliation.md)
- [49-customer-onboarding-workflow.md](02-business-workflows/49-customer-onboarding-workflow.md)
- [50-kyc-workflow.md](02-business-workflows/50-kyc-workflow.md)
- [51-credit-eligibility-workflow.md](02-business-workflows/51-credit-eligibility-workflow.md)
- [52-installment-collection-workflow.md](02-business-workflows/52-installment-collection-workflow.md)
- [53-missed-payment-workflow.md](02-business-workflows/53-missed-payment-workflow.md)
- [54-chargeback-dispute-workflow.md](02-business-workflows/54-chargeback-dispute-workflow.md)
- [55-merchant-onboarding-workflow.md](02-business-workflows/55-merchant-onboarding-workflow.md)
- [56-merchant-refund-workflow.md](02-business-workflows/56-merchant-refund-workflow.md)
- [57-customer-support-escalation-workflow.md](02-business-workflows/57-customer-support-escalation-workflow.md)
- [58-fraud-detection-workflow.md](02-business-workflows/58-fraud-detection-workflow.md)
- [59-account-suspension-workflow.md](02-business-workflows/59-account-suspension-workflow.md)
- [60-account-recovery-workflow.md](02-business-workflows/60-account-recovery-workflow.md)

### 03 — BNPL & Financing
- [12-bnpl-product-specification.md](03-bnpl-financing/12-bnpl-product-specification.md)
- [13-payment-plan-rules.md](03-bnpl-financing/13-payment-plan-rules.md)
- [14-eligibility-rules.md](03-bnpl-financing/14-eligibility-rules.md)
- [15-credit-limit-rules.md](03-bnpl-financing/15-credit-limit-rules.md)
- [16-financing-state-machine.md](03-bnpl-financing/16-financing-state-machine.md)
- [77-financing-model.md](03-bnpl-financing/77-financing-model.md)
- [78-installment-state-machine.md](03-bnpl-financing/78-installment-state-machine.md)
- [79-financing-calculation-specification.md](03-bnpl-financing/79-financing-calculation-specification.md)

### 04 — Shariah *(INTERNAL DRAFT — pending Shariah board review)*
- [17-shariah-product-structure.md](04-shariah/17-shariah-product-structure.md)
- [18-shariah-governance.md](04-shariah/18-shariah-governance.md)
- [19-shariah-review-register.md](04-shariah/19-shariah-review-register.md) — **contains the platform's one confirmed live non-compliance item**
- [80-shariah-principles-constraints.md](04-shariah/80-shariah-principles-constraints.md)
- [81-shariah-compliance-requirements.md](04-shariah/81-shariah-compliance-requirements.md)
- [82-shariah-advisor-board.md](04-shariah/82-shariah-advisor-board.md)
- [83-shariah-review-process.md](04-shariah/83-shariah-review-process.md)
- [84-shariah-audit-process.md](04-shariah/84-shariah-audit-process.md)
- [85-shariah-non-compliance-handling.md](04-shariah/85-shariah-non-compliance-handling.md)
- [86-product-change-shariah-review.md](04-shariah/86-product-change-shariah-review.md)

### 05 — Architecture
- [20-system-architecture.md](05-architecture/20-system-architecture.md)
- [21-service-responsibility-matrix.md](05-architecture/21-service-responsibility-matrix.md)
- [22-microservice-documentation.md](05-architecture/22-microservice-documentation.md) (index) → [microservices/](05-architecture/microservices/): [gateway](05-architecture/microservices/gateway.md), [product-service](05-architecture/microservices/product-service.md), [credit-engine](05-architecture/microservices/credit-engine.md), [payment-orchestrator](05-architecture/microservices/payment-orchestrator.md), [ledger-service](05-architecture/microservices/ledger-service.md), [notification-service](05-architecture/microservices/notification-service.md)

### 06 — API & Events
- [23-api-standards.md](06-api-events/23-api-standards.md)
- [24-event-catalog.md](06-api-events/24-event-catalog.md)
- [118-api-architecture.md](06-api-events/118-api-architecture.md)
- [119-api-versioning.md](06-api-events/119-api-versioning.md)
- [120-error-standards.md](06-api-events/120-error-standards.md)
- [121-pagination-standards.md](06-api-events/121-pagination-standards.md)
- [122-idempotency-standards.md](06-api-events/122-idempotency-standards.md)
- [123-webhook-standards.md](06-api-events/123-webhook-standards.md)
- [124-external-integration-documentation.md](06-api-events/124-external-integration-documentation.md)
- [125-event-driven-architecture.md](06-api-events/125-event-driven-architecture.md)
- [126-event-schema.md](06-api-events/126-event-schema.md)
- [127-event-ownership.md](06-api-events/127-event-ownership.md)
- [128-retry-dead-letter-strategy.md](06-api-events/128-retry-dead-letter-strategy.md)
- [129-idempotency-strategy-events.md](06-api-events/129-idempotency-strategy-events.md)
- [130-event-ordering-rules.md](06-api-events/130-event-ordering-rules.md)

### 07 — Database
- [25-database-architecture.md](07-database/25-database-architecture.md)
- [26-database-dictionary.md](07-database/26-database-dictionary.md)
- [131-er-diagram.md](07-database/131-er-diagram.md)
- [132-database-schema-documentation.md](07-database/132-database-schema-documentation.md)
- [133-data-ownership.md](07-database/133-data-ownership.md)
- [134-migration-standards.md](07-database/134-migration-standards.md)
- [135-database-backup-recovery.md](07-database/135-database-backup-recovery.md)

### 08 — Security
- [27-security-architecture.md](08-security/27-security-architecture.md)
- [28-kyc-verification-workflow.md](08-security/28-kyc-verification-workflow.md)
- [29-authentication-authorization.md](08-security/29-authentication-authorization.md)
- [136-kyb-architecture.md](08-security/136-kyb-architecture.md)
- [137-session-management.md](08-security/137-session-management.md)
- [138-secrets-management.md](08-security/138-secrets-management.md)
- [139-encryption-standard.md](08-security/139-encryption-standard.md)
- [140-security-threat-model.md](08-security/140-security-threat-model.md)
- [141-fraud-account-takeover-prevention.md](08-security/141-fraud-account-takeover-prevention.md)
- [142-security-incident-response.md](08-security/142-security-incident-response.md)

### 09 — QA & Testing
- [30-qa-strategy.md](09-qa/30-qa-strategy.md)
- [31-test-case-repository.md](09-qa/31-test-case-repository.md)
- [32-financial-transaction-test-strategy.md](09-qa/32-financial-transaction-test-strategy.md)
- [143-test-strategy.md](09-qa/143-test-strategy.md)
- [144-api-testing-strategy.md](09-qa/144-api-testing-strategy.md)
- [145-ui-testing-strategy.md](09-qa/145-ui-testing-strategy.md)
- [146-integration-testing.md](09-qa/146-integration-testing.md)
- [147-end-to-end-testing.md](09-qa/147-end-to-end-testing.md)
- [148-ledger-testing.md](09-qa/148-ledger-testing.md)
- [149-payment-failure-testing.md](09-qa/149-payment-failure-testing.md)
- [150-refund-testing.md](09-qa/150-refund-testing.md)
- [151-fraud-testing.md](09-qa/151-fraud-testing.md)
- [152-security-testing.md](09-qa/152-security-testing.md)
- [153-performance-testing.md](09-qa/153-performance-testing.md)
- [154-uat-process.md](09-qa/154-uat-process.md)
- [155-release-acceptance-criteria.md](09-qa/155-release-acceptance-criteria.md)

### 10 — DevOps & Infrastructure
- [33-infrastructure-architecture.md](10-devops/33-infrastructure-architecture.md)
- [34-deployment-process.md](10-devops/34-deployment-process.md)
- [35-monitoring-logging.md](10-devops/35-monitoring-logging.md)
- [156-environment-strategy.md](10-devops/156-environment-strategy.md)
- [157-cicd-documentation.md](10-devops/157-cicd-documentation.md)
- [158-rollback-process.md](10-devops/158-rollback-process.md)
- [159-secrets-config-management.md](10-devops/159-secrets-config-management.md)
- [160-alerting.md](10-devops/160-alerting.md)
- [161-disaster-recovery.md](10-devops/161-disaster-recovery.md)
- [162-backup-restore.md](10-devops/162-backup-restore.md)
- [163-business-continuity.md](10-devops/163-business-continuity.md)

### 11 — Compliance & Regulatory *(INTERNAL DRAFT — pending legal review)*
- [36-compliance-requirements-matrix.md](11-compliance/36-compliance-requirements-matrix.md) — **notes SahulatKar's actual SECP licensing status is unconfirmed anywhere in this repo**
- [37-kyc-aml-policy.md](11-compliance/37-kyc-aml-policy.md)
- [38-responsible-financing-policy.md](11-compliance/38-responsible-financing-policy.md)
- [164-licensing-regulatory-assessment.md](11-compliance/164-licensing-regulatory-assessment.md)
- [165-customer-due-diligence.md](11-compliance/165-customer-due-diligence.md)
- [166-transaction-monitoring.md](11-compliance/166-transaction-monitoring.md)
- [167-fraud-financial-crime-policy.md](11-compliance/167-fraud-financial-crime-policy.md)
- [168-consumer-protection-policy.md](11-compliance/168-consumer-protection-policy.md)
- [169-data-protection-compliance.md](11-compliance/169-data-protection-compliance.md)
- [170-complaints-grievance-procedure.md](11-compliance/170-complaints-grievance-procedure.md)
- [171-record-retention-policy.md](11-compliance/171-record-retention-policy.md)
- [172-regulatory-reporting-procedure.md](11-compliance/172-regulatory-reporting-procedure.md)
- [173-compliance-monitoring.md](11-compliance/173-compliance-monitoring.md)

### 12 — Operations & Support
- [39-customer-support-sop.md](12-operations/39-customer-support-sop.md)
- [40-merchant-vendor-support-sop.md](12-operations/40-merchant-vendor-support-sop.md)
- [41-incident-response-plan.md](12-operations/41-incident-response-plan.md)
- [174-kyc-escalation-sop.md](12-operations/174-kyc-escalation-sop.md)
- [175-payment-failure-sop.md](12-operations/175-payment-failure-sop.md)
- [176-refund-sop.md](12-operations/176-refund-sop.md)
- [177-default-sop.md](12-operations/177-default-sop.md)
- [178-fraud-escalation-sop.md](12-operations/178-fraud-escalation-sop.md)
- [179-account-suspension-sop.md](12-operations/179-account-suspension-sop.md)
- [180-account-recovery-sop.md](12-operations/180-account-recovery-sop.md)
- [181-complaint-escalation-matrix.md](12-operations/181-complaint-escalation-matrix.md)

### 13 — Analytics & Reporting
- [42-kpi-metrics-dictionary.md](13-analytics/42-kpi-metrics-dictionary.md)
- [182-product-metrics-dictionary.md](13-analytics/182-product-metrics-dictionary.md)
- [183-bnpl-kpis.md](13-analytics/183-bnpl-kpis.md)
- [184-merchant-kpis.md](13-analytics/184-merchant-kpis.md)
- [185-credit-risk-kpis.md](13-analytics/185-credit-risk-kpis.md)
- [186-financial-kpis.md](13-analytics/186-financial-kpis.md)
- [187-operations-kpis.md](13-analytics/187-operations-kpis.md)
- [188-executive-dashboard-specification.md](13-analytics/188-executive-dashboard-specification.md)

### 14 — Project Management
- [43-product-roadmap.md](14-project-management/43-product-roadmap.md)
- [44-architecture-decision-records.md](14-project-management/44-architecture-decision-records.md)
- [203-release-plan.md](14-project-management/203-release-plan.md)
- [204-sprint-planning-process.md](14-project-management/204-sprint-planning-process.md)

### 15 — Product Requirements
- [45-prd.md](15-product-requirements/45-prd.md)
- [46-feature-requirements.md](15-product-requirements/46-feature-requirements.md)
- [47-user-stories.md](15-product-requirements/47-user-stories.md)
- [48-acceptance-criteria.md](15-product-requirements/48-acceptance-criteria.md)

### 16 — Customer Documentation
- [61-customer-persona.md](16-customer-documentation/61-customer-persona.md)
- [62-customer-lifecycle.md](16-customer-documentation/62-customer-lifecycle.md)
- [63-customer-states-statuses.md](16-customer-documentation/63-customer-states-statuses.md)
- [64-customer-experience-specification.md](16-customer-documentation/64-customer-experience-specification.md)

### 17 — Merchant Documentation *(mostly "not applicable" by design — read [`65-merchant-overview.md`](17-merchant-documentation/65-merchant-overview.md) first)*
- [65-merchant-overview.md](17-merchant-documentation/65-merchant-overview.md)
- [66-merchant-lifecycle.md](17-merchant-documentation/66-merchant-lifecycle.md)
- [67-merchant-onboarding-requirements.md](17-merchant-documentation/67-merchant-onboarding-requirements.md)
- [68-merchant-verification-kyb.md](17-merchant-documentation/68-merchant-verification-kyb.md)
- [69-merchant-dashboard-requirements.md](17-merchant-documentation/69-merchant-dashboard-requirements.md)
- [70-merchant-checkout-flow.md](17-merchant-documentation/70-merchant-checkout-flow.md) — the one genuinely rich technical document in this folder
- [71-merchant-order-flow.md](17-merchant-documentation/71-merchant-order-flow.md)
- [72-merchant-settlement-flow.md](17-merchant-documentation/72-merchant-settlement-flow.md)
- [73-merchant-refund-flow.md](17-merchant-documentation/73-merchant-refund-flow.md)
- [74-merchant-dispute-flow.md](17-merchant-documentation/74-merchant-dispute-flow.md)
- [75-merchant-commission-fee-model.md](17-merchant-documentation/75-merchant-commission-fee-model.md) — **the one unresolved question in this folder; needs Business Development input**
- [76-merchant-integration-guide.md](17-merchant-documentation/76-merchant-integration-guide.md)

### 18 — Credit & Risk Policy
- [87-credit-risk-framework.md](18-credit-risk-policy/87-credit-risk-framework.md)
- [88-eligibility-engine-specification.md](18-credit-risk-policy/88-eligibility-engine-specification.md)
- [89-credit-scoring-model-documentation.md](18-credit-risk-policy/89-credit-scoring-model-documentation.md)
- [90-credit-decision-rules.md](18-credit-risk-policy/90-credit-decision-rules.md)
- [91-credit-limit-algorithm.md](18-credit-risk-policy/91-credit-limit-algorithm.md)
- [92-risk-segmentation.md](18-credit-risk-policy/92-risk-segmentation.md)
- [93-fraud-risk-framework.md](18-credit-risk-policy/93-fraud-risk-framework.md)
- [94-fraud-detection-rules.md](18-credit-risk-policy/94-fraud-detection-rules.md)
- [95-fraud-investigation-workflow.md](18-credit-risk-policy/95-fraud-investigation-workflow.md)
- [96-risk-override-policy.md](18-credit-risk-policy/96-risk-override-policy.md)
- [97-credit-policy.md](18-credit-risk-policy/97-credit-policy.md)
- [98-collections-recovery-policy.md](18-credit-risk-policy/98-collections-recovery-policy.md)

### 19 — Payments & Financial Operations
- [99-payment-architecture.md](19-payments-financial-operations/99-payment-architecture.md)
- [100-payment-lifecycle.md](19-payments-financial-operations/100-payment-lifecycle.md)
- [101-payment-gateway-integration-specification.md](19-payments-financial-operations/101-payment-gateway-integration-specification.md)
- [102-payment-reconciliation.md](19-payments-financial-operations/102-payment-reconciliation.md)
- [103-failed-payment-handling.md](19-payments-financial-operations/103-failed-payment-handling.md)
- [104-settlement-schedule.md](19-payments-financial-operations/104-settlement-schedule.md)
- [105-payment-retry-rules.md](19-payments-financial-operations/105-payment-retry-rules.md)
- [106-refund-rules.md](19-payments-financial-operations/106-refund-rules.md)
- [107-reversal-rules.md](19-payments-financial-operations/107-reversal-rules.md)
- [108-chargeback-dispute-process.md](19-payments-financial-operations/108-chargeback-dispute-process.md)

### 20 — Ledger & Accounting
- [109-ledger-architecture.md](20-ledger-accounting/109-ledger-architecture.md)
- [110-chart-of-accounts.md](20-ledger-accounting/110-chart-of-accounts.md)
- [111-double-entry-accounting-model.md](20-ledger-accounting/111-double-entry-accounting-model.md)
- [112-transaction-types.md](20-ledger-accounting/112-transaction-types.md)
- [113-ledger-invariants.md](20-ledger-accounting/113-ledger-invariants.md) — **the single most important document in this category; several invariants are currently unenforced**
- [114-ledger-entry-specification.md](20-ledger-accounting/114-ledger-entry-specification.md)
- [115-balance-calculation.md](20-ledger-accounting/115-balance-calculation.md)
- [116-reconciliation-process.md](20-ledger-accounting/116-reconciliation-process.md)
- [117-financial-reporting.md](20-ledger-accounting/117-financial-reporting.md)

### 21 — Business & Merchant Operations *(mostly "not applicable" — see category 17 for why)*
- [189-merchant-acquisition-process.md](21-business-merchant-operations/189-merchant-acquisition-process.md)
- [190-merchant-pricing-model.md](21-business-merchant-operations/190-merchant-pricing-model.md)
- [191-merchant-commission-structure.md](21-business-merchant-operations/191-merchant-commission-structure.md)
- [192-merchant-contract.md](21-business-merchant-operations/192-merchant-contract.md)
- [193-merchant-settlement-agreement.md](21-business-merchant-operations/193-merchant-settlement-agreement.md)
- [194-merchant-risk-policy.md](21-business-merchant-operations/194-merchant-risk-policy.md)
- [195-merchant-suspension-policy.md](21-business-merchant-operations/195-merchant-suspension-policy.md)
- [196-merchant-onboarding-sop.md](21-business-merchant-operations/196-merchant-onboarding-sop.md)
- [197-merchant-integration-sop.md](21-business-merchant-operations/197-merchant-integration-sop.md)

### 22 — Incident Management
- [198-incident-management-policy.md](22-incident-management/198-incident-management-policy.md)
- [199-incident-severity-matrix.md](22-incident-management/199-incident-severity-matrix.md)
- [200-financial-incident-response.md](22-incident-management/200-financial-incident-response.md)
- [201-data-breach-response.md](22-incident-management/201-data-breach-response.md)
- [202-postmortem-template.md](22-incident-management/202-postmortem-template.md)

## The gaps that show up everywhere

A handful of findings from `docs/PRODUCTION_GAPS_REPORT.md` (2026-04-27) recur across dozens of these documents because they're structurally central to the platform. If you only remember five things from this whole knowledge base:

1. **No service publishes `loan.created`** — every signed Murabaha contract is missing its foundational ledger entries. ([`20-ledger-accounting/109-ledger-architecture.md`](20-ledger-accounting/109-ledger-architecture.md))
2. **The checkout automation can't complete a purchase end-to-end** — the payment-form-filling step is an incomplete stub. This is the platform's core value proposition, currently non-functional. ([`05-architecture/microservices/product-service.md`](05-architecture/microservices/product-service.md))
3. **The ledger's debit=credit invariant is not enforced in code.** ([`20-ledger-accounting/113-ledger-invariants.md`](20-ledger-accounting/113-ledger-invariants.md))
4. **Refunds have no implementation anywhere in the system.** ([`02-business-workflows/09-refund-cancellation-workflow.md`](02-business-workflows/09-refund-cancellation-workflow.md))
5. **SahulatKar's actual SECP licensing status is not recorded anywhere in this repository.** ([`11-compliance/164-licensing-regulatory-assessment.md`](11-compliance/164-licensing-regulatory-assessment.md))

## Scope note

This knowledge base covers the full 23-category structure originally scoped, at a level appropriate to the platform's current build stage: architecture, workflows, and technical specs are detailed and code-grounded; several policy documents (Shariah governance, AML/compliance, incident management, business continuity) are explicitly marked **PLANNED** because the underlying process doesn't exist yet — those documents propose a starting structure rather than describing working practice. Two categories (05 — Merchant Documentation, 21 — Business & Merchant Operations) are intentionally thin because they don't apply to SahulatKar's vendor-agnostic model; each document explains why rather than being padded with invented content.

Not yet built out: a complete, table-by-table database dictionary for all ~169 tables (26/132 cover the ~30 tables referenced across other documents; the full schema lives in the Alembic migrations, deliberately not duplicated here — see [`07-database/132-database-schema-documentation.md`](07-database/132-database-schema-documentation.md)), and full ADR backfill for every historical architecture decision (7 seed ADRs exist in [`14-project-management/44-architecture-decision-records.md`](14-project-management/44-architecture-decision-records.md); new decisions should be added there going forward, at decision time).
