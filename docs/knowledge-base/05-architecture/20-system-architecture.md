# System Architecture Overview

**Status:** STABLE — this document also reconciles a discrepancy between two source documents; see "A note on conflicting readiness figures" below.

## High-level diagram

```
                    Next.js web-customer / web-admin
                              │
                          Gateway (BFF)
              Auth · KYC orchestration · RBAC · Hard Gates · Routing
                              │
      ┌───────────┬───────────┼───────────┬───────────┐
      │           │           │           │           │
  Product      Credit      Payment      Ledger    Notification
  Service      Engine    Orchestrator   Service      Service
      │           │           │           │           │
      └───────────┴───────────┴───────────┴───────────┘
                              │
                    PostgreSQL 16 (system of record)
                              │
                    Redis 7 (cache / pub-sub / queues)
                              │
        External: NADRA · TASDEEQ · Stripe Issuing · Safepay ·
        JazzCash · EasyPaisa · AfterShip · Rye API · BrightData · OpenAI
```

## Architectural style

**Domain-Driven Design with strictly bounded contexts**, 6 FastAPI microservices + 2 Next.js frontends, deployed as a monorepo (`apps/`, `packages/`, `infra/`, `db/`, `docs/`). Gateway acts as the single entry point / Backend-for-Frontend, orchestrating auth and enforcing hard gates before any downstream call.

## Communication patterns

- **Synchronous (REST/HTTP):** internal service-to-service calls via `httpx.AsyncClient`, authenticated with a shared `X-Internal-Token` HMAC. Used for real-time lookups (e.g., Gateway fetching a product price from Product Service).
- **Asynchronous (Redis Pub/Sub):** real-time state synchronization across services (e.g., `payment.down_payment_confirmed` triggering VCN issuance). Full catalog: [`../06-api-events/24-event-catalog.md`](../06-api-events/24-event-catalog.md).
- **Background workers (Redis-backed queues / BullMQ):** durable task execution for high-latency work — web scraping, checkout automation, billing sweeps.

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, Python 3.12 |
| Frontend | Next.js 14, React 18, Tailwind, shadcn/ui |
| Primary DB | PostgreSQL 16 (RDS, r6g.xlarge, 32GB) + TimescaleDB (co-located, for tracking events) |
| Cache/Queue | Redis 7 + BullMQ (ElastiCache, 3-node) |
| Connection pooling | PgBouncer, transaction-mode (2000 client → 180 PG connections) |
| Automation | Playwright + playwright-stealth + BrightData residential proxies |
| Agent scaling | KEDA on EKS (0 → 100 pods, queue-depth driven) |
| VCN issuance | Stripe Issuing (MVP) → Lithic (planned, at scale) |
| Payments | Safepay, JazzCash, EasyPaisa, Raast (planned) |
| ML | XGBoost + LightGBM + CatBoost + Isolation Forest |
| LLM | GPT-4o Vision (primary), Groq Llama-3-70B (alternative) |
| Infra | AWS `ap-south-1` — EKS, ECR, RDS, S3, ElastiCache |
| CI/CD | GitHub Actions → ECR → EKS rolling deploy |

Full detail: [`../10-devops/33-infrastructure-architecture.md`](../10-devops/33-infrastructure-architecture.md).

## Unified security model

1. **Edge:** NGINX Ingress, SSL/TLS, rate limiting.
2. **Identity:** RS256 JWT, session tracking in Redis.
3. **Hard gates:** workflow-level enforcement (e.g., VCN blocked without `contracts_signed`).
4. **Internal auth:** cross-service calls require a shared, KMS-stored `X-Internal-Token`.
5. **Data security:** PII (CNIC, phone, VCN) encrypted at rest via `pgcrypto` AES-256.

Full detail: [`../08-security/27-security-architecture.md`](../08-security/27-security-architecture.md).

## Observability (as designed)

Standardized JSON structured logging, Prometheus `/metrics` per service, `X-Request-ID` propagation for distributed tracing, liveness/readiness health probes checking DB/Redis/listener health. **Known gap:** per the code audit, `X-Request-ID` is generated at the Gateway but not actually propagated to downstream services, and no Grafana dashboards, Fluent Bit log shipping, or OpenTelemetry tracing collector are configured yet — the design intent above is not yet operational. Full detail: [`../10-devops/35-monitoring-logging.md`](../10-devops/35-monitoring-logging.md).

## A note on conflicting readiness figures

Two source documents in this repository describe system readiness very differently, and a reader should know why:

- `docs/audits/global_system_audit.md` (undated in-file, architecture-level) states core microservices are "95% Fully implemented logic, hardening complete" and Database Migrations "100%."
- `docs/PRODUCTION_GAPS_REPORT.md` (dated 2026-04-27, explicitly "every Python file across all services" read) puts overall platform completion at **~55%**, with named critical bugs (e.g., a scraping worker that crashes on every job) and 14 launch-blocking gaps.

This knowledge base treats **`PRODUCTION_GAPS_REPORT.md` as the more reliable source for current implementation state**, because it is line-item verified against actual code with file/line references, while the global audit reads as an architecture-completeness assessment (the *design* is fully specified) rather than a functional-correctness audit (whether the code *runs*). Both can be simultaneously true: the architecture is comprehensively speced and scaffolded, while a meaningful fraction of that scaffolding does not yet function end-to-end. Anyone using either document should be aware of this distinction — "the architecture is done" and "the platform is done" are different claims here.

## Related documents

[`21-service-responsibility-matrix.md`](21-service-responsibility-matrix.md), [`22-microservice-documentation.md`](22-microservice-documentation.md), [`../07-database/25-database-architecture.md`](../07-database/25-database-architecture.md), [`../10-devops/33-infrastructure-architecture.md`](../10-devops/33-infrastructure-architecture.md).
