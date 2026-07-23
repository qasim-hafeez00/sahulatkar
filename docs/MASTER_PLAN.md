# SAHULATKAR — MASTER IMPLEMENTATION PLAN
# Enterprise End-to-End: Code → Push → CI/CD → Deploy

> **PURPOSE**: Paste this file into every new AI chat session to provide full system context.
> **Last Updated**: 2026-04-08
> **Status**: Phase 1 in progress — skeleton scaffolded, credit-engine partially implemented.

---

## TABLE OF CONTENTS

1. [System Overview](#1-system-overview)
2. [Current State Assessment](#2-current-state-assessment)
3. [Repository Structure](#3-repository-structure)
4. [Implementation Phases](#4-implementation-phases)
5. [Phase 1: Foundation](#5-phase-1-foundation)
6. [Phase 2: Core Business Logic](#6-phase-2-core-business-logic)
7. [Phase 3: Integrations & Scale](#7-phase-3-integrations--scale)
8. [Phase 4: Production Readiness](#8-phase-4-production-readiness)
9. [Git Workflow & Branching](#9-git-workflow--branching)
10. [CI/CD Pipeline](#10-cicd-pipeline)
11. [Infrastructure Pipeline](#11-infrastructure-pipeline)
12. [Testing Strategy](#12-testing-strategy)
13. [Iteration Checklist](#13-iteration-checklist)
14. [Environment Management](#14-environment-management)
15. [Monitoring & Observability](#15-monitoring--observability)
16. [Security Checklist](#16-security-checklist)

---

## 1. SYSTEM OVERVIEW

**SahulatKar** — Pakistan's first vendor-agnostic, Shariah-compliant BNPL platform.
User pastes any product URL → AI agent buys it → user repays in installments under Murabaha contract.

### Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI (Python 3.12), 6 microservices |
| Frontend | Next.js 14 + React 18 + Tailwind + shadcn/ui |
| Primary DB | PostgreSQL 16 (RDS) + TimescaleDB |
| Cache/Queue | Redis 7 + BullMQ (ElastiCache 3-node) |
| Agent | Playwright + playwright-stealth + BrightData |
| VCN | Stripe Issuing → Lithic (scale) |
| Payments | Safepay + JazzCash + EasyPaisa + Raast |
| ML | XGBoost + LightGBM + CatBoost + Isolation Forest |
| Infra | AWS ap-south-1 (EKS, ECR, RDS, S3, ElastiCache) |
| CI/CD | GitHub Actions → ECR → EKS rolling deploy |
| Pool | PgBouncer transaction-mode |

### 6 Core Microservices

| # | Service | Port | Redis DB | Owns |
|---|---|---|---|---|
| 1 | Gateway API | 8000 | 0 | Auth, JWT, RBAC, rate-limit, hard gates |
| 2 | Product Service | 8001 | 1 | URL pipeline, extraction, UPO |
| 3 | Credit Engine | 8002 | 2 | 7-layer scoring, fraud, limits |
| 4 | Payment Orchestrator | 8003 | 3 | VCN, Safepay, JazzCash, reconciliation |
| 5 | Ledger Service | 8004 | 4 | Double-entry, installments, charity |
| 6 | Notification Service | 8005 | 5 | SMS, WhatsApp, push, email |

### 2 Frontends

| App | Port | Purpose |
|---|---|---|
| web-customer | 3000 | Customer-facing Next.js app |
| web-admin | 3001 | Admin dashboard (20 modules) |

### 12-Step Order Flow (IMMUTABLE)

```
1. User pastes URL → Gateway → Product Service
2. Playwright + BrightData scrapes merchant page
3. GPT-4o Vision extracts Universal Product Object (UPO)
4. XGBoost credit assessment < 3 seconds
5. Financing offer: cost + 4% markup disclosed
6. User signs Wakalah Agreement via OTP
7. User signs Murabaha Contract via OTP  ← HARD GATE
8. Down payment collected (25–40%)
9. Single-use VCN issued (MCC-locked) ← BLOCKED UNTIL STEP 7
10. Playwright agent completes checkout
11. Delivery tracked via AfterShip
12. Remaining installments auto-collected biweekly
```

### 3 Shariah Rules (DB-Enforced, NEVER skip in CI)

1. **Late Fee Charity**: 100% donated — zero retained by platform
2. **Cost Price Disclosure**: `murabaha_contracts` has NOT NULL on `cost_price`, `profit_amount`, `profit_rate_pct`
3. **Prohibited Categories**: Blocked before any offer — logged to immutable `prohibited_items_log`

**HARD GATE**: VCN issuance requires `order.status == "contracts_signed"` — Gateway returns HTTP 403 `MURABAHA_NOT_SIGNED` otherwise. This test runs in CI on every push.

---

## 2. CURRENT STATE ASSESSMENT

### What EXISTS (Completed)

| Component | Status | Notes |
|---|---|---|
| Monorepo structure | ✅ Done | `apps/`, `packages/`, `infra/`, `db/`, `docs/`, `.github/` |
| `packages/shared-python` | ✅ Done | Extensive models, constants, db, redis, storage, events |
| Credit Engine (M04) | ✅ Done | Layers, services, workers, ML pipeline |
| Gateway API (M01, M02) | ✅ Done | Endpoints for Auth, KYC, Orders, Payments, Admin routes |
| Payment Orchestrator | ✅ Done | Safepay, Jazzcash, VCN worker |
| Product Service (M03) | ✅ Done | Playwright extractors, pricing, url normalizer, checkout agent |
| Ledger Service (M11) | ✅ Done | Accounts, billing sweeps, TASDEEQ integration |
| Notification Service | ✅ Done | Aftership webhooks, tracking service |
| CI/CD Pipeline | ✅ Done | GitHub actions for CI, tests, and build-and-push |
| Docker & Compose | ✅ Done | Fully functional |
| K8s Manifests | ✅ Done | Base, KEDA, and Production/Staging Overlays |
| Terraform | ✅ Done | Modules (VPC, EKS, RDS, Redis, S3, IAM, KMS) fully provisioned |
| System Specs & Docs | ✅ Done | M01-M12 defined |
| Alembic Migrations | 🟡 Partial | `001` - `011` completed. (Missing `012` to `016`) |
| web-customer | 🟡 Partial | Scaffolded Next.js. UI pending |
| web-admin | 🟡 Partial | Scaffolded Next.js. UI pending |

### What is MISSING / INCOMPLETE

- **Database Migrations (`012` - `016`)**: Audit trails, System settings, Triggers, Indexes, and Data Seeding.
- **Frontend Applications**: `web-admin` (M12) full component implementation and `web-customer` customer journey screens.
- **Observability Stack**: Prometheus + Grafana implementation, Fluent Bit logging, OpenTelemetry tracing.
- **Security Hardening & External Testing**: Load testing, Pen-testing, and compliance documentation.
- **In-depth E2E Integration Tests**: Playwright cross-service e2e tests simulating the full 12-step flow.

### Junk / Irrelevant Files Identified
- `Sahulatkar-docs/SahulatKar_Admin_Documentation.docx`
- `Sahulatkar-docs/SahulatKar_DB_Design_Volume1.docx`
- `Sahulatkar-docs/SahulatKar_DB_Design_Volume2.docx`
- `Sahulatkar-docs/SahulatKar_KYC_Fraud_Research.docx`
- `Sahulatkar-docs/SahulatKar_Payment_Delivery_Research.docx`
- `Sahulatkar-docs/SahulatKar_URL_Pipeline_Research.docx`
*(These .docx files are redundant to their .txt counterparts and will remain ignored.)*

---

## 3. REPOSITORY STRUCTURE

```
sahulatkar/
├── .github/workflows/
│   ├── ci.yml                    # Lint + Test + Migration check
│   └── build-and-push.yml        # Docker build → ECR → EKS deploy
├── apps/
│   ├── gateway/                  # M01: Auth, RBAC, routing
│   ├── product-service/          # M03: URL pipeline, UPO
│   ├── credit-engine/            # M04: 7-layer scoring
│   ├── payment-orchestrator/     # M06-M07: Payments, VCN
│   ├── ledger-service/           # M11: Double-entry, installments
│   ├── notification-service/     # Notification: SMS, push, email
│   ├── web-customer/             # Next.js customer app
│   └── web-admin/                # Next.js admin dashboard
├── packages/
│   ├── shared-python/            # sk_shared: models, constants, utils
│   └── shared-ts/                # Shared TypeScript types
├── db/migrations/                # Alembic migrations (single source of truth)
├── infra/
│   ├── docker/                   # docker-compose.yml, PG init, PgBouncer
│   ├── k8s/                      # Kustomize: base/ + overlays/{staging,prod}
│   └── terraform/                # modules/ + environments/{staging,prod}
├── scripts/                      # Dev utilities, seed data, migration helpers
└── docs/                         # All documentation (consolidated)
    ├── System-md-files/          # Module specs (M01-M12)
    ├── Sahulatkar-docs/          # Research documents
    ├── audits/                   # Per-service + global engineering audits
    ├── mutation-testing/         # Mutation-testing assignment artifacts
    └── MASTER_PLAN.md            # THIS FILE
```

### Service Internal Structure (Python)

Each Python microservice follows this layout:
```
apps/{service}/
├── Dockerfile
├── pyproject.toml
├── src/
│   ├── main.py                   # FastAPI app + lifespan
│   ├── config.py                 # Pydantic Settings
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py             # Router aggregator
│   │   └── v1/                   # Versioned endpoint modules
│   ├── core/
│   │   ├── dependencies.py       # get_db, get_redis, get_current_user
│   │   └── security.py           # JWT validation, RBAC
│   ├── models/                   # Service-specific SQLAlchemy (imports from sk_shared)
│   ├── schemas/                  # Pydantic request/response models
│   ├── services/                 # Business logic layer
│   └── workers/                  # Background tasks, queue consumers
└── tests/
    ├── conftest.py               # Fixtures: test DB, mock Redis
    ├── test_api/                  # Endpoint tests
    └── test_services/            # Unit tests
```

---

## 4. IMPLEMENTATION PHASES

```
Phase 1 (Weeks 1-10)  — FOUNDATION: Auth, KYC, URL Pipeline, Credit Engine, Contracts
Phase 2 (Weeks 11-18) — CORE BIZ: Payments, VCN, Checkout Agent, HITL
Phase 3 (Weeks 19-24) — SCALE: Delivery, Ledger, Admin, Notifications
Phase 4 (Weeks 25-30) — PRODUCTION: Observability, Security hardening, Load testing, Launch
```

---

## 5. PHASE 1 — FOUNDATION (Sprints S01-S06)

### Sprint S01: Shared Infrastructure + Gateway Auth (Weeks 3-4)

**Iteration 1A — Shared Python package hardening**
```
Files to create/modify:
  packages/shared-python/sk_shared/models/__init__.py    — export all models
  packages/shared-python/sk_shared/models/auth.py        — User, AdminUser, UserSession, UserDevice
  packages/shared-python/sk_shared/security.py           — JWT encode/decode, password hashing
  packages/shared-python/sk_shared/redis_client.py       — async Redis wrapper with namespace
  packages/shared-python/sk_shared/exceptions.py         — Shared exception hierarchy
  packages/shared-python/sk_shared/middleware.py          — CORS, request ID, logging middleware
  packages/shared-python/sk_shared/pagination.py         — Cursor + offset pagination helpers
  db/migrations/versions/002_init_m01_auth.py             — Auth tables migration
```

**Iteration 1B — Gateway API service**
```
Files to create/modify:
  apps/gateway/src/main.py             — Full FastAPI app with lifespan
  apps/gateway/src/config.py           — Settings: JWT keys, rate limits
  apps/gateway/src/core/security.py    — JWT middleware, RBAC decorator
  apps/gateway/src/core/dependencies.py — get_db, get_redis, get_current_user
  apps/gateway/src/api/v1/auth.py      — register, verify-otp, login, refresh, logout
  apps/gateway/src/api/v1/admin_auth.py — admin login with TOTP
  apps/gateway/src/services/auth.py    — OTP generation, session management
  apps/gateway/src/services/rbac.py    — Role-permission matrix
  apps/gateway/src/schemas/auth.py     — Pydantic schemas
  apps/gateway/tests/conftest.py       — Test fixtures
  apps/gateway/tests/test_api/test_auth.py — Auth endpoint tests
```

**Push checklist for S01:**
- [ ] `ruff check` passes on all Python
- [ ] `mypy --strict` passes on shared-python
- [ ] Unit tests pass: `pytest apps/gateway/tests/ -v`
- [ ] Migration runs: `alembic upgrade head` (against test PG)
- [ ] Docker build succeeds: `docker build -f apps/gateway/Dockerfile .`
- [ ] Health check returns 200: `GET /health`

### Sprint S02-S03: KYC & NADRA (Weeks 5-8)

**Iteration 2A — KYC models + Gateway KYC endpoints**
```
Files:
  packages/shared-python/sk_shared/models/kyc.py          — UserKycVerification, KycVerificationQueue
  apps/gateway/src/api/v1/kyc.py                           — /kyc/start, /kyc/verify-cnic, /kyc/verify-liveness
  apps/gateway/src/services/kyc.py                         — KYC orchestration, S3 presigned URLs
  apps/gateway/src/services/nadra.py                       — NADRA Verisys client (mock initially)
  apps/gateway/src/services/shufti.py                      — Shufti Pro OCR/liveness client (mock)
  db/migrations/versions/003_init_m02_kyc.py
```

**Iteration 2B — KYC manual review + admin endpoints**
```
Files:
  apps/gateway/src/api/v1/admin_kyc.py                     — /admin/kyc/{id}/decision
  apps/gateway/src/services/kyc_queue.py                    — Manual review queue management
  apps/gateway/tests/test_api/test_kyc.py
```

### Sprint S04: Credit Engine Completion (Weeks 9-10)

**Iteration 3A — Complete 7-layer pipeline with real DB**
```
Files to complete:
  apps/credit-engine/src/layers/layer1_hard_blocks.py      — Redis blacklist check
  apps/credit-engine/src/layers/layer2_velocity.py         — Redis sliding window
  apps/credit-engine/src/layers/layer3_identity.py         — KYC signal scoring
  apps/credit-engine/src/layers/layer4_alt_data.py         — JazzCash API mock
  apps/credit-engine/src/layers/layer5_ml_scoring.py       — XGBoost dummy model
  apps/credit-engine/src/layers/layer6_order_overlay.py    — Product category risk
  apps/credit-engine/src/layers/layer7_portfolio.py        — Concentration limits
  apps/credit-engine/src/services/pipeline.py              — Wire DB + Redis (replace mocks)
  apps/credit-engine/src/core/dependencies.py              — Real get_db, get_redis
  apps/credit-engine/src/ml/dummy_model.py                 — Pickle-loadable XGBoost stub
  apps/credit-engine/tests/test_pipeline.py                — Full pipeline test
```

### Sprint S05: Contracts (Weeks 11-12)

**Iteration 4A — Shariah contracts**
```
Files:
  packages/shared-python/sk_shared/models/contracts.py     — WakalahAgreement, MurabahaContract, ContractDigitalSignature
  apps/gateway/src/api/v1/contracts.py                      — generate + sign for both contracts
  apps/gateway/src/services/contract_generator.py           — ReportLab PDF generation
  apps/gateway/src/services/contract_signer.py              — OTP verification for signing
  db/migrations/versions/004_init_m05_contracts.py
  apps/gateway/tests/test_api/test_contracts.py
  apps/gateway/tests/test_hard_gate.py                      — MURABAHA_NOT_SIGNED test (NEVER xfail)
```

### Sprint S06: URL Pipeline / Product Service (Weeks 13-14)

**Iteration 5A — Product service core**
```
Files:
  packages/shared-python/sk_shared/models/product.py       — Product, ScrapingJob, Merchant, ProhibitedCategory
  apps/product-service/src/main.py                          — FastAPI app
  apps/product-service/src/api/v1/products.py               — /products/extract, /products/jobs/{id}
  apps/product-service/src/services/url_normalizer.py       — URL cleaning, platform detection
  apps/product-service/src/services/extraction_waterfall.py — Tier 1-4 waterfall
  apps/product-service/src/services/prohibited_checker.py   — Category classification
  apps/product-service/src/services/pricing.py              — Murabaha calculation
  db/migrations/versions/005_init_m03_products.py
```

---

## 6. PHASE 2 — CORE BUSINESS LOGIC (Sprints S07-S12)

### Sprint S07-S08: Payment Orchestrator + VCN (Weeks 15-18)

**Iteration 6A — Payment models + down payment flow**
```
Files:
  packages/shared-python/sk_shared/models/payment.py       — Loan, Installment, PaymentTransaction, VirtualCard
  apps/payment-orchestrator/src/api/v1/payments.py          — /payments/down-payment, /payments/pay-installment
  apps/payment-orchestrator/src/api/v1/webhooks.py          — /webhooks/safepay, /webhooks/jazzcash
  apps/payment-orchestrator/src/services/safepay.py         — Safepay gateway client
  apps/payment-orchestrator/src/services/jazzcash.py        — JazzCash direct API client
  apps/payment-orchestrator/src/services/vcn.py             — Stripe Issuing VCN lifecycle
  apps/payment-orchestrator/src/services/reconciliation.py  — Gateway settlement matching
  db/migrations/versions/006_init_m06_payments.py
```

### Sprint S09-S10: Checkout Agent (Weeks 19-20)

**Iteration 7A — Playwright checkout automation**
```
Files:
  apps/product-service/src/services/checkout_agent.py       — Playwright stealth checkout
  apps/product-service/src/services/self_healing.py          — VLM recovery via GPT-4o
  apps/product-service/src/workers/checkout_consumer.py      — BullMQ job consumer
  packages/shared-python/sk_shared/models/checkout.py        — PurchaseExecution
  db/migrations/versions/007_init_m08_checkout.py
```

### Sprint S11: HITL Queue (Weeks 21-22)

**Iteration 8A — Human-in-the-loop**
```
Files:
  packages/shared-python/sk_shared/models/hitl.py            — HitlQueue
  apps/gateway/src/api/v1/admin_hitl.py                       — /admin/hitl, /admin/hitl/{id}/claim, resolve
  db/migrations/versions/008_init_m09_hitl.py
```

---

## 7. PHASE 3 — INTEGRATIONS & SCALE (Sprints S13-S18)

### Sprint S13: Delivery Tracking

```
Files:
  packages/shared-python/sk_shared/models/delivery.py        — Shipment, TrackingEvent, Courier
  apps/notification-service/src/api/v1/tracking.py            — /tracking/{order_id}, /webhooks/aftership
  db/migrations/versions/009_init_m10_delivery.py
```

### Sprint S14-S15: Ledger & Billing

```
Files:
  packages/shared-python/sk_shared/models/ledger.py           — LedgerAccount, JournalEntry, JournalEntryLine, LateFeeCharityAllocation
  apps/ledger-service/src/services/double_entry.py             — Journal entry creation
  apps/ledger-service/src/services/billing_sweep.py            — Daily installment collection
  apps/ledger-service/src/services/charity_router.py           — Late fee → Edhi allocation
  apps/ledger-service/src/api/v1/admin_finance.py              — P&L, reconciliation, shariah report
  db/migrations/versions/010_init_m11_ledger.py
```

### Sprint S16-S18: Admin Dashboard + Notification Service

```
apps/web-admin/ — 20 admin modules (AD-01 through AD-28)
apps/notification-service/ — SMS (Jazz), WhatsApp, Push (Firebase), Email (SendGrid)
apps/web-customer/ — Customer journey screens (US-01 through US-20)
```

---

## 8. PHASE 4 — PRODUCTION READINESS & IN-DEPTH TESTING (Sprints S19-S22)

- [ ] **Comprehensive E2E Integration Suite**: Playwright end-to-end framework automating cross-service 12-step flow tests from `gateway` to `ledger-service`.
- [ ] **Chaos Engineering**: Inject faults (e.g., Redis down, DB locked, third-party timeouts) to ensure circuit breakers + dead letter queues (DLQ) work.
- [ ] Load testing: k6 scripts targeting 1000 concurrent users.
- [ ] Security audit: OWASP top 10 checklist.
- [ ] Penetration testing on payment flows & VCN isolation.
- [ ] SECP regulatory documentation.
- [ ] Shariah board contract certification.
- [ ] Data residency verification (Pakistan - ap-south-1).
- [ ] Disaster recovery runbook setup and execution simulation.
- [ ] On-call rotation and alerting framework.

---

## 8.5. PHASE 5 — FUTURE GAPS & ENHANCEMENTS

- [ ] **Dynamic Extraction Failover**: Replace deterministic Playwright extractors with self-hosted LLMs/VLMs completely for long-tail unmapped merchants.
- [ ] **Anti-Fraud Information Sharing**: Build modular integration capability for cross-platform fraud sharing networks in Pakistan.
- [ ] **Micro-Frontend Architecture**: If the Next.js `web-admin` outgrows its bounds, slice 20 modules into MFEs.
- [ ] **Multi-Region Resiliency**: Evolve AWS architecture from standard active-standby to Multi-Region Active-Active as transaction scale limits out of ap-south-1.

## 9. GIT WORKFLOW & BRANCHING

```
main          ← production-ready, protected, requires PR + 1 approval + CI green
  └── develop ← integration branch, receives feature merges
       └── feature/{service}/{ticket}  ← individual work
       └── fix/{service}/{ticket}      ← bug fixes
       └── infra/{component}           ← infrastructure changes
```

### Branch Naming Convention
```
feature/gateway/s01-auth-register
feature/credit-engine/s04-layer5-ml
fix/payment-orchestrator/webhook-idempotency
infra/terraform-rds-setup
infra/ci-docker-build
```

### Commit Message Format
```
feat(gateway): implement OTP registration flow
fix(credit-engine): correct velocity window calculation
chore(ci): add Docker build step to CI pipeline
docs(specs): update M04 credit bands table
test(gateway): add auth endpoint integration tests
infra(k8s): add credit-engine deployment manifest
```

### PR Rules
- Title: `[SERVICE] Brief description`
- Body: What + Why + Testing done
- Requires: CI green + 1 approval (self-approve OK for solo dev)
- Squash merge to develop, merge commit to main

---

## 10. CI/CD PIPELINE

### CI Pipeline (`.github/workflows/ci.yml`) — Runs on every push + PR

```yaml
# STAGE 1: Lint (parallel per service)
python-lint:
  matrix: [gateway, product-service, credit-engine, payment-orchestrator, ledger-service, notification-service]
  steps:
    - ruff check apps/${{ matrix.service }}/
    - mypy apps/${{ matrix.service }}/src/ --ignore-missing-imports

# STAGE 2: Unit Tests (after lint passes)
python-test:
  needs: python-lint
  matrix: [gateway, product-service, credit-engine, payment-orchestrator, ledger-service, notification-service]
  services:
    postgres: timescale/timescaledb:2.14.2-pg16
    redis: redis:7.2-alpine
  steps:
    - pip install -e packages/shared-python[test]
    - pip install -e apps/${{ matrix.service }}[test]
    - pytest apps/${{ matrix.service }}/tests/ -v --cov --cov-fail-under=80

# STAGE 3: Frontend (parallel)
frontend-test:
  matrix: [web-customer, web-admin]
  steps:
    - npm ci
    - npm run lint
    - npm run type-check
    - npm test -- --coverage

# STAGE 4: Migration Check
migration-check:
  needs: python-lint
  services:
    postgres: timescale/timescaledb:2.14.2-pg16
  steps:
    - alembic upgrade head
    - alembic downgrade -1
    - alembic upgrade head  # verify reversibility

# STAGE 5: Hard Gate Test (NEVER skip)
hard-gate-test:
  needs: python-test
  steps:
    - pytest apps/gateway/tests/test_hard_gate.py -v --tb=short

# STAGE 6: Docker Build (verify all Dockerfiles build)
docker-build:
  needs: [python-test, frontend-test]
  matrix: [gateway, product-service, credit-engine, payment-orchestrator, ledger-service, notification-service, web-customer, web-admin]
  steps:
    - docker build -f apps/${{ matrix.service }}/Dockerfile -t sk-${{ matrix.service }}:ci .
```

### CD Pipeline (`.github/workflows/build-and-push.yml`) — Runs on merge to main

```yaml
# STAGE 1: Detect changed services
detect-changes:
  outputs: changed_services (list of services with file changes)

# STAGE 2: Build + Push to ECR (only changed services)
build-push:
  matrix: ${{ needs.detect-changes.outputs.changed_services }}
  steps:
    - aws ecr get-login-password | docker login
    - docker build -f apps/${{ matrix.service }}/Dockerfile -t $ECR_REGISTRY/sk-${{ matrix.service }}:${{ github.sha }} .
    - docker push $ECR_REGISTRY/sk-${{ matrix.service }}:${{ github.sha }}
    - docker tag ... :latest && docker push :latest

# STAGE 3: Deploy to Staging
deploy-staging:
  needs: build-push
  steps:
    - aws eks update-kubeconfig --name sk-staging
    - kustomize build infra/k8s/overlays/staging | kubectl apply -f -
    - kubectl rollout status deployment/sk-${{ matrix.service }} -n sahulatkar --timeout=300s

# STAGE 4: Smoke Tests on Staging
smoke-test:
  needs: deploy-staging
  steps:
    - curl -f https://staging-api.sahulatkar.com/health
    - pytest tests/smoke/ -v

# STAGE 5: Deploy to Production (manual approval gate)
deploy-production:
  needs: smoke-test
  environment: production  # requires manual approval in GitHub
  steps:
    - aws eks update-kubeconfig --name sk-production
    - kustomize build infra/k8s/overlays/production | kubectl apply -f -
    - kubectl rollout status ... --timeout=300s
```

---

## 11. INFRASTRUCTURE PIPELINE

### Terraform Flow

```
infra/terraform/
├── modules/
│   ├── vpc/          — VPC, subnets, NAT, security groups
│   ├── eks/          — EKS cluster, node groups, IRSA
│   ├── rds/          — PostgreSQL 16, read replica, parameter groups
│   ├── elasticache/  — Redis 7, 3-node cluster
│   ├── ecr/          — 8 repositories (one per service)
│   ├── s3/           — Buckets: contracts, kyc-images, screenshots, static
│   ├── iam/          — Service roles, policies, OIDC
│   ├── kms/          — Encryption keys for PII
│   └── pgbouncer/    — ECS task for PgBouncer
└── environments/
    ├── staging/main.tf    — Smaller instances, single AZ
    └── production/main.tf — Multi-AZ, r6g.xlarge, 3-node Redis
```

### Terraform CI (add to ci.yml)
```yaml
terraform-validate:
  steps:
    - terraform init -backend=false
    - terraform validate
    - terraform fmt -check
    - tflint --recursive
```

### K8s Manifests (Kustomize)

```
infra/k8s/
├── base/
│   ├── {service}/
│   │   ├── deployment.yaml     — 2 replicas, resource limits, health probes
│   │   ├── service.yaml        — ClusterIP
│   │   ├── hpa.yaml            — Min 2, Max 10, CPU 70%
│   │   └── kustomization.yaml
│   └── pgbouncer/
│       └── deployment.yaml
├── keda/
│   └── scaled-objects.yaml     — Checkout agent 0→100 based on queue length
└── overlays/
    ├── staging/
    │   ├── kustomization.yaml  — 1 replica, smaller resources
    │   └── patches/
    └── production/
        ├── kustomization.yaml  — 2+ replicas, full resources, PDB
        └── patches/
```

---

## 12. TESTING STRATEGY

### Test Pyramid

```
                    ┌─────────┐
                    │  E2E    │  5%  — Playwright browser tests
                   ┌┴─────────┴┐
                   │Integration │ 25% — API tests with real DB + Redis
                  ┌┴───────────┴┐
                  │  Unit Tests  │ 70% — Pure function, mock I/O
                  └──────────────┘
```

### Required Tests Per Service (before merge)

| Test Type | Tool | Minimum Coverage |
|---|---|---|
| Unit | pytest | 80% line coverage |
| Integration | pytest + testcontainers | All API endpoints |
| Lint | ruff | Zero violations |
| Type check | mypy | No errors (--ignore-missing-imports) |
| Security | bandit | No high-severity findings |
| Frontend unit | vitest | 70% coverage |
| Frontend E2E | Playwright | Critical paths |

### Critical Path Tests (NEVER mark xfail)

1. `test_murabaha_hard_gate` — VCN blocked without signed contract
2. `test_late_fee_charity` — 100% routed to charity
3. `test_prohibited_category_block` — alcohol/tobacco/gambling blocked
4. `test_cost_price_disclosure` — Murabaha contract has all 3 NOT NULL fields
5. `test_credit_sla` — Credit check completes < 3 seconds

---

## 13. ITERATION CHECKLIST

**Use this checklist BEFORE every `git push`:**

```markdown
## Pre-Push Checklist

### Code Quality
- [ ] `ruff check .` — zero violations
- [ ] `mypy src/ --ignore-missing-imports` — zero errors
- [ ] No hardcoded secrets (grep for passwords, keys, tokens)
- [ ] No `print()` statements — use `logging` module
- [ ] All new endpoints have Pydantic request/response schemas

### Tests
- [ ] `pytest tests/ -v` — all pass
- [ ] Coverage ≥ 80% on changed files
- [ ] Hard gate test still passes
- [ ] New endpoints have at least 1 happy + 1 error test

### Database
- [ ] New migration file if models changed
- [ ] Migration is reversible (has downgrade)
- [ ] All monetary fields use DECIMAL(14,2) — NEVER float
- [ ] New tables have `created_at`, `updated_at`
- [ ] Sensitive fields encrypted (CNIC, IBAN, VCN)

### Docker
- [ ] `docker build -f apps/{service}/Dockerfile .` succeeds
- [ ] Image < 500MB
- [ ] Runs as non-root user

### Documentation
- [ ] API docstrings on all new endpoints
- [ ] README updated if setup steps changed
- [ ] CHANGELOG entry for user-facing changes

### CI/CD
- [ ] CI pipeline passes locally (act or manual)
- [ ] No secrets in committed code
- [ ] Feature flag for incomplete features
```

---

## 14. ENVIRONMENT MANAGEMENT

### Environments

| Env | Purpose | DB | URL |
|---|---|---|---|
| local | Development | docker-compose PG | localhost:8000 |
| test | CI automated tests | testcontainers PG | N/A |
| staging | Pre-production | RDS staging | staging-api.sahulatkar.com |
| production | Live | RDS production | api.sahulatkar.com |

### Required Environment Variables (`.env` template)

```bash
# Database
DATABASE_URL=postgresql+asyncpg://sk_app:${PG_PASSWORD}@pgbouncer:6432/sahulatkar
PG_PASSWORD=

# Redis
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
REDIS_PASSWORD=

# JWT
JWT_PRIVATE_KEY=          # RS256 PEM
JWT_PUBLIC_KEY=
JWT_ACCESS_TTL=900        # 15 min
JWT_REFRESH_TTL=86400     # 24 hr

# External APIs
NADRA_API_KEY=
NADRA_API_URL=
SHUFTI_CLIENT_ID=
SHUFTI_SECRET_KEY=
STRIPE_SECRET_KEY=
SAFEPAY_API_KEY=
JAZZCASH_MERCHANT_ID=
JAZZCASH_PASSWORD=
AFTERSHIP_API_KEY=
OPENAI_API_KEY=
BRIGHTDATA_PROXY_URL=

# AWS
AWS_REGION=ap-south-1
S3_BUCKET_CONTRACTS=
S3_BUCKET_KYC=
ECR_REGISTRY=

# Feature Flags
FF_JAZZCASH_ENABLED=false
FF_RAAST_ENABLED=false
FF_LITHIC_VCN=false
```

### Secret Management
- **Local**: `.env` file (gitignored)
- **CI**: GitHub Actions secrets
- **Staging/Prod**: AWS Secrets Manager → K8s ExternalSecrets

---

## 15. MONITORING & OBSERVABILITY

### Stack
```
Metrics:    Prometheus + Grafana  (EKS addon)
Logging:    Fluent Bit → CloudWatch Logs → OpenSearch
Tracing:    OpenTelemetry → Jaeger / X-Ray
Alerting:   Grafana Alerting → Slack + PagerDuty
Uptime:     AWS Route 53 health checks
```

### Key Dashboards
1. **Service Health** — request rate, error rate, latency p50/p95/p99
2. **Credit Engine** — scoring latency, approval rate, band distribution
3. **Payment Flow** — success rate per gateway, reconciliation status
4. **Queue Depth** — BullMQ queue sizes, consumer lag
5. **Database** — connection pool usage, query latency, replication lag
6. **Business KPIs** — GMV, active users, default rate, revenue

### Alerting Rules (PagerDuty)
- Error rate > 5% for 5 min → P1
- Credit Engine p99 > 3s → P2
- Payment webhook failures > 3 in 10 min → P1
- Database connection pool > 80% → P2
- Redis memory > 90% → P2
- Pod restart count > 3 in 15 min → P2

---

## 16. SECURITY CHECKLIST

- [ ] All PII encrypted at rest (pgcrypto AES-256)
- [ ] All API endpoints authenticated (except /health, /auth/register, /auth/verify-otp)
- [ ] Rate limiting on all public endpoints
- [ ] HMAC-SHA256 on all webhook endpoints
- [ ] CORS restricted to known origins
- [ ] SQL injection prevention (parameterized queries via SQLAlchemy)
- [ ] XSS prevention (Next.js default + CSP headers)
- [ ] CSRF tokens on state-changing frontend requests
- [ ] Secrets never in code, logs, or error responses
- [ ] VCN PAN/CVV never logged — only masked numbers
- [ ] Admin endpoints require MFA (TOTP)
- [ ] Audit trail on all sensitive operations
- [ ] Data residency: all data stays in AWS ap-south-1
- [ ] PECA 2016 compliance: OTP-based e-signatures

---

## SPRINT EXECUTION ORDER FOR AI CHAT SESSIONS

When starting a new chat, paste this file and specify which sprint/iteration to work on:

```
"Implement Sprint S01 Iteration 1A — Shared Python package hardening.
Reference MASTER_PLAN.md sections 5 and 3 for file list and structure.
Reference System-md-files/M01-auth.md for Auth module spec."
```

### Recommended Session Sequence

| Session | Work | Key Reference Files |
|---|---|---|
| 1 | S01-1A: Shared Python models (auth) | M01-auth.md, models/base.py |
| 2 | S01-1B: Gateway auth endpoints | M01-auth.md |
| 3 | S02-2A: KYC models + endpoints | M02-kyc.md |
| 4 | S02-2B: KYC manual review | M02-kyc.md |
| 5 | S04-3A: Credit engine layers | M04-credit-engine.md |
| 6 | S05-4A: Contracts (Wakalah + Murabaha) | M05-contracts.md |
| 7 | S06-5A: Product service / URL pipeline | M03-url-pipeline.md |
| 8 | CI/CD: Real CI pipeline | Section 10 of this file |
| 9 | CI/CD: Docker builds + ECR push | Section 10 of this file |
| 10 | Infra: Terraform modules | Section 11 of this file |
| 11 | Infra: K8s manifests | Section 11 of this file |
| 12 | S07-6A: Payment orchestrator | M06-M09 spec |
| 13 | S09-7A: Checkout agent | M06-M09 spec |
| 14 | S13: Delivery tracking | M10-M12 spec |
| 15 | S14-15: Ledger engine | M10-M12 spec |
| 16 | S16-18: Admin dashboard | M10-M12 spec |
| 17 | S16-18: Customer frontend | Design screens |
| 18 | Observability: Prometheus + Grafana | Section 15 |
| 19 | Security hardening | Section 16 |
| 20 | Load testing + launch prep | Phase 4 |

---

## IMMUTABLE RULES (NEVER VIOLATE)

1. **HARD GATE**: VCN issuance requires `contracts_signed` — test in CI
2. **DECIMAL(14,2)** for all monetary — NEVER float/double
3. **Late fees → 100% charity** — DB trigger enforced
4. **Cost price disclosure** — 3 NOT NULL fields on murabaha_contracts
5. **Prohibited categories** — block before any offer
6. **CNIC/IBAN/VCN encrypted** — AES-256 via pgcrypto
7. **PAN/CVV never logged** — masked in all outputs
8. **All migrations reversible** — downgrade path required
9. **No secrets in code** — environment variables only
10. **Data residency Pakistan** — AWS ap-south-1 only
