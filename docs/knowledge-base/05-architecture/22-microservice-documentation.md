# Microservice Documentation — Index

**Status:** STABLE

One document per backend microservice, in [`microservices/`](microservices/):

| Service | Document | Module spec source |
|---|---|---|
| Gateway | [`microservices/gateway.md`](microservices/gateway.md) | M01 (auth), M02 (KYC), M05 (contracts) |
| Product Service | [`microservices/product-service.md`](microservices/product-service.md) | M03 (URL pipeline), M08 (checkout agent) |
| Credit Engine | [`microservices/credit-engine.md`](microservices/credit-engine.md) | M04 |
| Payment Orchestrator | [`microservices/payment-orchestrator.md`](microservices/payment-orchestrator.md) | M06 (payments), M07 (VCN) |
| Ledger Service | [`microservices/ledger-service.md`](microservices/ledger-service.md) | M11 |
| Notification Service | [`microservices/notification-service.md`](microservices/notification-service.md) | M09 (HITL, shared), M10 (delivery) |

The two frontends (`web-customer`, `web-admin`) are not separately documented here as "services" — see [`20-system-architecture.md`](20-system-architecture.md) for their place in the architecture and `docs/System-md-files/M12-admin.md` (source spec) for the 20 admin modules (AD-01 through AD-28).

Each service document covers: purpose, responsibilities, dependencies, APIs, events, database ownership, and known gaps (with gap IDs traceable to `docs/PRODUCTION_GAPS_REPORT.md`).
