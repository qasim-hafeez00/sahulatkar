# SahulatKar 🇵🇰

**Pakistan's first vendor-agnostic, Shariah-compliant Buy Now, Pay Later (BNPL) platform.**

SahulatKar enables users to paste any product URL, have an AI agent purchase the item, and then repay in scheduled installments under a strictly Shariah-compliant Murabaha contract.

---

## 🏗 System Architecture

The platform operates on a modernized microservices architecture running on AWS EKS, utilizing **FastAPI (Python 3.12)** for backend services and **Next.js 14** for frontend applications.

### Core Stack
- **Backend**: FastAPI, SQLAlchemy, Pydantic, Alembic
- **Frontend**: Next.js 14, React 18, TailwindCSS, shadcn/ui
- **Primary Database**: PostgreSQL 16 (TimescaleDB extension) + PgBouncer (Transaction mode)
- **Caching & Queues**: Redis 7, BullMQ (pub/sub & async workers)
- **AI/Agents**: Groq/GPT-4o Vision, Playwright, BrightData, XGBoost
- **Infrastructure**: AWS (EKS, ECR, RDS, ElastiCache, S3), Terraform, Kustomize

---

## 📂 Repository Structure

This is a monorepo containing everything from the frontend web apps to the infrastructure-as-code definitions.

### Applications (`apps/`)

| Service / App | Port | Description |
|---|---|---|
| **gateway** | 8000 | API Gateway. Handles authentication (JWT), RBAC, hard gates, OTP, and request routing. |
| **product-service** | 8001 | URL processing pipeline. Handles extraction, platform detection, and the Playwright checkout agent. |
| **credit-engine** | 8002 | 7-layer scoring pipeline assessing fraud, identity, velocity, and applying ML model limits. |
| **payment-orchestrator** | 8003 | Integrates with Stripe (VCN), Safepay, and JazzCash. Handles payment reconciliation. |
| **ledger-service** | 8004 | Double-entry accounting system managing installments, billing sweeps, and late-fee charity mapping. |
| **notification-service**| 8005 | Manages external multi-channel notifications (SMS, WhatsApp, emails) and AfterShip delivery hooks. |
| **web-customer** | 3000 | Customer-facing Next.js application. |
| **web-admin** | 3001 | Complex back-office operation dashboard with 20+ modules (HITL, Ledger reporting, KYC manual review, etc.). |

### Packages (`packages/`)
- **`shared-python/`**: Reusable Python packages containing all SQLAlchemy database models (single source of truth), custom exception classes, Redis pub/sub wrappers, and queue consumer bases.
- **`shared-ts/`**: Shared TypeScript definitions aligning Next.js frontend with backend schemas.

### Infrastructure & Operations
- **`db/`**: Contains Alembic database migrations (`versions/`). The single source of truth for schema evolution.
- **`infra/docker/`**: Docker Compose configurations and PG initialization scripts for local deployment.
- **`infra/k8s/`**: Kubernetes manifests via Kustomize (base, production, staging overlays, and KEDA configurations).
- **`infra/terraform/`**: Modularized Terraform setups (VPC, EKS, RDS, Redis, S3, ECR) to provision environments.
- **`scripts/`**: Utility scripts for data seeding, dev setups, and ad-hoc operations.

### Documentation & Specifications
- **`MASTER_PLAN.md` & `MASTER_PLAN_DETAILED.md`**: Core reference documents defining implementation phases, constraints, architectures, and guidelines. (Required to be injected into LLM chat sessions).
- **`System-md-files/`**: System module specifications (M01-M12).
- **`docs/`**: Generated system API documentation and runbooks.

---

## ⚙️ The 12-Step Immutable Flow

Every order strictly adheres to this pipeline to maintain system integrity and Shariah compliance:

1. User pastes URL → Gateway API → Product Service.
2. Playwright + BrightData securely scrapes the merchant page.
3. GPT-4o Vision creates a Universal Product Object (UPO).
4. Credit Engine assesses user credit limit synchronously (sub-3 seconds).
5. Financing offer generated (cost + markup explicitly disclosed).
6. User signs Wakalah Agreement (via OTP).
7. **HARD GATE**: User signs Murabaha Contract (via OTP).
8. Down payment collected securely.
9. Single-use VCN issued (MCC-locked, amount-locked). Needs contracts signed.
10. Checkout Agent automates the physical purchase on the merchant’s website.
11. Delivery tracked natively via Notification Service (AfterShip).
12. Ledger sweeps remaining installments biweekly.

### 🕌 Shariah Compliance Rules (DB-Enforced)
- **Late Fee Charity**: 100% of all late fees are auto-donated. None is retained.
- **Transparency**: The cost price, profit amount, and profit percentage are hardcoded into the DB schema on the contract.
- **Prohibited Categories**: Gambling, alcohol, and prohibited goods are blocked via ML text categorization.

---

## 🚀 Getting Started (Development)

### Prerequisites
- Python 3.12+
- Node.js 20+
- Docker & Docker Compose
- PostgreSQL 16 (or rely on docker container)

### Setup Instructions

1. **Start Infrastructure Services**:
   ```bash
   docker-compose -f infra/docker/docker-compose.yml up -d postgres redis pgbouncer
   ```

2. **Initialize Database**:
   ```bash
   # Make sure you are using a virtual environment
   pip install -r requirements.txt # Adjust per package structure
   cd db/ && alembic upgrade head
   ```

3. **Install Dependencies**:
   Shared components must be installed first.
   ```bash
   pip install -e packages/shared-python
   pip install -e apps/gateway # Repeat for desired microservices
   ```
   
   For the Next.js apps:
   ```bash
   cd apps/web-admin && npm i
   ```

4. **Environment Variables**:
   Copy the respective `.env.example` templates to `.env` per service. Sensitive API keys for external integrations (Safepay, Stripe, etc.) are required for full integration testing.

5. **Run Services**:
   Standard FastAPI start command.
   ```bash
   fastapi dev apps/gateway/src/main.py --port 8000
   ```

---

## ✔️ Testing Strategy

The repository utilizes the test pyramid:
- **Unit & Integration**: `pytest` tests inside each application's `tests/` directory leveraging `testcontainers` for DB/Redis isolation.
- **Frontend**: Vitest and Playwright.
- **Code Quality**: `ruff` for linting, `mypy --strict` for static type checking across all internal APIs.

*All PRs to `develop` must pass 80% coverage and zero `mypy`/`ruff` warnings.*
