# SahulatKar: System Overview & Audit Index

**Last verified:** 2026-08-28

## Purpose of this folder

`docs/audits/` is the integration reference for SahulatKar's backend — written for whoever builds the next frontend (the previous `web-customer`/`web-admin` Next.js apps are being discarded and rebuilt from scratch) and for that person's own AI coding agent. Each doc below is grounded in the actual current code, not aspirational claims — where something is genuinely unverified or incomplete, the doc says so rather than rounding up. Start with **[web_apps_audit.md](web_apps_audit.md)** — it's now a from-scratch frontend integration guide, not a description of the old apps — then read the per-service doc for whichever backend area you're integrating against.

| Doc | Covers |
|---|---|
| [web_apps_audit.md](web_apps_audit.md) | **Frontend integration guide** — customer journey, admin modules, auth model, polling patterns, dev-only shortcuts. Read this first. |
| [gateway_microservice_audit.md](gateway_microservice_audit.md) | The single BFF every frontend talks to. Full endpoint catalog, order state machine, security controls, Redis key/queue/pub-sub reference, RBAC matrix. |
| [product_service_audit.md](product_service_audit.md) | URL extraction, Murabaha pricing, autonomous Playwright checkout agent. |
| [credit_engine_audit.md](credit_engine_audit.md) | Risk scoring pipeline, credit limits, fraud/blacklist checks. |
| [payment_orchestrator_audit.md](payment_orchestrator_audit.md) | VCN (virtual card) issuance, JazzCash/SafePay/Stripe integration, installment collection. |
| [ledger_service_audit.md](ledger_service_audit.md) | Double-entry accounting, billing sweep, charity routing, finance reporting APIs. |
| [notification_service_audit.md](notification_service_audit.md) | Shipment tracking, multi-channel dispatch. |
| [infrastructure_packages_audit.md](infrastructure_packages_audit.md) | Running the full stack locally, `sk_shared` package, migrations, CI/CD, deployment infra. |

For an unvarnished list of known bugs and gaps (with file:line references and fix status), see `docs/PRODUCTION_GAPS_REPORT_2026-08.md` — it's the primary source most of the "known gaps" sections in these docs were verified against.

---

## 1. What SahulatKar is

A Pakistani, vendor-agnostic, Shariah-compliant Buy Now Pay Later (BNPL) platform. A customer pastes the URL of a product from (in principle) any online merchant; the platform extracts the product, prices a Murabaha (cost-plus-sale) financing offer, runs KYC and credit checks, has the customer sign a Wakalah (agency) agreement and then the Murabaha contract, issues a single-use virtual card, and autonomously executes the purchase on the merchant's own checkout page via a backend browser-automation agent — no merchant-side integration required.

## 2. Architecture

Six independent microservices, one shared Python package, one Postgres database (TimescaleDB extension), Redis (separate logical DB per service — see `infrastructure_packages_audit.md`), all orchestrated via `docker compose` locally.

| Service | Owns |
|---|---|
| **Gateway** | The only public HTTP surface. Auth, KYC orchestration, order lifecycle, contracts, admin back-office, webhooks, internal callback ingestion. |
| **Product Service** | URL → product extraction (multi-tier waterfall: paid data APIs → JSON-LD → Playwright scraping), Murabaha pricing, the autonomous checkout agent. |
| **Credit Engine** | Multi-layer risk scoring, credit limit/down-payment decisioning, fraud/blacklist checks. |
| **Payment Orchestrator** | Virtual card (VCN) issuance via Stripe Issuing, JazzCash/SafePay down-payment and installment collection, webhook ingestion from all payment providers. |
| **Ledger Service** | Double-entry bookkeeping, billing sweep, charity routing for late fees, reconciliation, TASDEEQ credit-bureau reporting. |
| **Notification Service** | AfterShip-backed shipment tracking, SMS/push/email dispatch. |

**Communication**: synchronous HTTP (`httpx`, internal-token-authenticated) for real-time cross-service calls; Redis lists (`LPUSH`/`BRPOP`) for durable work queues; Redis pub/sub for event fan-out. As of 2026-08, the Payment Orchestrator's outbox publisher was rewritten onto Redis Streams consumer groups (`XADD`/`XREADGROUP`/`XACK`) for durable delivery — plain pub/sub had no durability guarantee and could silently drop financial events if a consumer was down.

**No service other than Gateway is meant to be called by a frontend.** See `web_apps_audit.md` section 1.

## 3. Shariah compliance mechanics

- **Wakalah** (agency agreement) must be signed before the **Murabaha** (cost-plus-sale) contract can be generated; Murabaha signing is what actually creates the loan and installment schedule.
- **Cost transparency**: Murabaha contracts disclose `cost_price` and `profit_amount` explicitly (tiered nominal rates: 2.5% for 3-month, 7.0% for 6-month, 12.0% for 12-month plans, targeting a consistent ~4% annualized effective markup).
- **Late fees are never revenue** — they post to a `charity_payable` liability account and are disbursed to Edhi Foundation via a dedicated worker, never recognized as company income. Enforced in the ledger's accounting layer, not just policy.
- **Prohibited categories** (tobacco, alcohol, gambling) are blocked by keyword matching at order-initiation time in Gateway and again in Product Service.
- Whether `validated_by_shariah_board` claims on generated contracts are backed by a real, recorded board-approval process is a real open question — check the current disposition in `gateway_microservice_audit.md`'s findings section rather than assuming.

## 4. Testing

Each service has its own unit/integration test suite (mocked neighbors, SQLite-backed for the Python services). As of 2026-08-28, a genuine **cross-service end-to-end test** also exists: `tests/e2e/test_order_lifecycle.py`, run via `pytest tests/e2e/` — it brings up the full `docker compose` stack (real Postgres, real Redis, real Docker networking, a real Playwright browser against a bundled mock-merchant fixture) and walks registration through a verified, balanced ledger entry with zero mocking. It passes (`1 passed in ~208s`) and is the single most reliable ground-truth reference for exact request/response shapes across the whole platform — see `tests/e2e/README.md`.

Building that test surfaced and fixed several real, previously-undiscovered production bugs that no per-service mocked test suite could have caught — most notably a missing PgBouncer compatibility flag in Ledger Service's own database engine that could silently drop real financial postings in any deployment behind PgBouncer (fixed; see `ledger_service_audit.md` section 6), and multiple cases of SQLAlchemy models declaring columns that no Alembic migration had actually created (ORM/schema drift). If you hit an `UndefinedColumnError` or a silently-failing write anywhere in this codebase, check for this class of bug first.

## 5. Known gaps as of 2026-08-28

The 12 previously-identified CRITICAL findings (double-charge risk, non-durable financial event delivery, a billing-sweep crash on the normal overdue case, credit scoring running on mocked/dead signals, SSRF/cardholder-data exposure risks, and several broken admin flows) have been fixed and verified against each service's test suite. 16 HIGH-severity and a longer tail of MEDIUM findings remain — see `docs/PRODUCTION_GAPS_REPORT_2026-08.md` for the full, current list with file:line references, and the "Known Gaps" section of each per-service doc in this folder for the subset relevant to frontend integration specifically. Nothing in this repository has been re-audited wholesale beyond what these docs describe — treat any claim you can't find grounded in a specific file as unverified.
