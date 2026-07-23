# SahulatKar: Global System-Wide Audit & Architectural Report

## 1. Executive Summary

SahulatKar is a production-hardened, Shariah-compliant Buy Now Pay Later (BNPL) platform architected as a distributed microservices ecosystem. The system is designed for massive scale, modularity, and strict regulatory compliance (SECP/PECA 2016).

This global audit consolidates the architectural integrity, cross-service communication patterns, and security frameworks implemented across all 6 core microservices and 2 frontend applications.

---

## 2. High-Level System Architecture

SahulatKar follows a **Domain-Driven Design (DDD)** approach with strictly bounded contexts.

### Architectural Core
- **BFF (Backend for Frontend)**: The Gateway Service acts as the single entry point, orchestrating authentication and enforcing "Hard Gates" before downstream service invocation.
- **Asynchronous Execution**: High-latency tasks (web scraping, credit assessment, VCN issuance) are offloaded to background workers via Redis-backed queues.
- **Event-Driven Propagation**: Microservices communicate via a Redis Pub/Sub event bus (e.g., `payment.confirmed` triggers `ledger.post`).

### Service Map
| Service | Domain | Responsibilities |
|---|---|---|
| **Gateway** | Identity | Auth, KYC, Contracts, Hard Gates, RBAC |
| **Product** | Catalog | URL Extraction (Playwright), UPO Generation, Checkout Automation |
| **Credit** | Risk | 7-layer Scoring, Fraud detection, Credit limits |
| **Payment** | Finance | VCN Lifecycle (Stripe), JazzCash/SafePay, Reconciliation |
| **Ledger** | Accounting | Double-entry bookkeeping, Billing sweeps, Charity routing |
| **Notification** | Comms | AfterShip tracking, SMS/WhatsApp/Push/Email dispatch |

---

## 3. Communication Patterns

### Synchronous (REST/HTTP)
Internal service-to-service calls use `httpx.AsyncClient` with a shared `Internal-Token` HMAC validation for security. This pattern is primarily used for real-time lookups (e.g., Gateway fetching product price from Product Service).

### Asynchronous (Redis Pub/Sub & Workers)
Durable background processing is handled via:
- **Pub/Sub**: Used for real-time state synchronization across services (e.g., `order.delivered` triggering `Wakalah` execution).
- **BullMQ/Background Workers**: Used for reliable task execution (e.g., `CheckoutConsumer` processing a Playwright purchase).

---

## 4. Unified Security Model

### Layered Defense
1. **Edge Security**: NGINX Ingress enforces SSL/TLS and rate-limiting.
2. **Identity Layer**: RS256 JWT tokens with singleton session tracking in Redis.
3. **Hard Gates**: Strict workflow enforcement (e.g., VCN blocking if `MURABAHA_NOT_SIGNED`).
4. **Internal Auth**: Cross-service calls require `X-Internal-Token` matching a shared KMS-stored secret.
5. **Data Security**: PII (CNIC, Phone, VCN) is encrypted at rest using `pgcrypto` (AES-256).

---

## 5. Observability & Production Hardening

Every service in the ecosystem implements the following standardized production features:
- **Standardized Logging**: JSON-formatted structured logging for ELK/CloudWatch compatibility.
- **Prometheus Metrics**: Explicit `/metrics` endpoints exposing latency, request counts, and business-specific counters.
- **Request Tracing**: `X-Request-ID` propagation across the entire call chain for distributed debugging.
- **Health Probing**: Liveness and Readiness checks measuring DB, Redis, and Listener health.

---

## 6. Shariah Compliance (Immutable Rules)

The platform implements technical safeguards for Shariah-compliant BNPL:
- **Charity Routing**: 100% of late fees are automatically routed to Edhi Foundation records (tracked in `LateFeeCharityAllocation`).
- **Cost Transparency**: `MurabahaContract` generation requires explicit `cost_price` and `profit_amount` disclosure.
- **Prohibited Categories**: Built-in blocklists in the URL Pipeline (Tobacco, Alcohol, Gambling).

---

## 7. Current Ecosystem Status

| Component | Readiness | Status |
|---|---|---|
| Core Microservices | 95% | Fully implemented logic, hardening complete. |
| Shared Packages | 100% | `sk-shared` provides unified models and security. |
| Database Migrations | 100% | Migration v42 establishes all 169+ tables. |
| Frontends | ~60% | Scaffolded. Admin core implemented; Customer UI in progress. |
| DevOps / Infrastructure | 90% | Terraform/K8s manifests ready for AWS deploy. |

---

## 8. Strategic Roadmap

1. **Global Observability Dashboard**: Consolidating per-service metrics into a unified Grafana dashboard.
2. **End-to-End Integration Suite**: Implementing cross-service Playwright tests for the 12-step "Golden Path".
3. **Full Frontend Maturity**: Completing the Customer-facing Next.js journey.
