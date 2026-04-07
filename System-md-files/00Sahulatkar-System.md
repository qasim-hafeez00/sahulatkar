# CLAUDE.md — SahulatKar System Knowledge Base

> Pakistan's first vendor-agnostic, Shariah-compliant BNPL platform.
> User pastes any product URL → AI agent buys it → user repays in installments under Murabaha contract.

---

## QUICK REFERENCE

| Param | Value |
|---|---|
| Markup | 4% flat, disclosed upfront |
| Down payment | 25–40% before VCN issuance |
| Plans | Pay-in-3, Pay-in-4, Pay-in-6 |
| Cold-start limit | PKR 3,000 → PKR 100,000 |
| Credit SLA | < 3 seconds (XGBoost) |
| KYC target | < 4 min Tier 1, < 10 min Tier 2 |
| Automation target | ≥ 80% end-to-end |
| Late fees | 100% donated to Edhi Foundation |
| DB tables | 169 across 13 domains |
| Core services | 6 microservices on EKS |

---

## STACK

| Layer | Tech |
|---|---|
| Backend | FastAPI (Python 3.12) |
| Frontend | Next.js 14 + React 18 + Tailwind + shadcn/ui |
| Primary DB | PostgreSQL 16 (RDS r6g.xlarge, 32GB) |
| Cache/Queue | Redis 7 + BullMQ (ElastiCache 3-node) |
| Agent | Playwright + playwright-stealth + BrightData |
| Agent Scale | KEDA on EKS (0→100 pods) |
| VCN MVP | Stripe Issuing → Lithic (scale) |
| Payments | Safepay + JazzCash + EasyPaisa + Raast |
| ML | XGBoost + Isolation Forest + GNN |
| LLM | GPT-4o Vision / Groq Llama-3-70B |
| Infra | AWS ap-south-1 (EKS, ECR, RDS, S3, ElastiCache) |
| CI/CD | GitHub Actions → ECR → EKS rolling |
| Time-series | TimescaleDB (co-located PG) |
| Pool | PgBouncer transaction-mode |

---

## 12-STEP ORDER FLOW (IMMUTABLE SEQUENCE)

```
1. User pastes URL → Frontend → Gateway → Product Service
2. Playwright + BrightData scrapes merchant page
3. GPT-4o Vision extracts Universal Product Object (UPO)
4. XGBoost credit assessment < 3 seconds
5. Financing offer: cost + 4% markup disclosed
6. User signs Wakalah Agreement via OTP
7. User signs Murabaha Contract via OTP  ← HARD GATE
8. Down payment collected (25–40%) via Safepay/JazzCash/Raast
9. Single-use VCN issued (MCC-locked, amount-capped) ← BLOCKED UNTIL STEP 7
10. Playwright agent completes checkout at merchant
11. Delivery tracked via AfterShip
12. Remaining installments auto-collected biweekly
```

**HARD GATE RULE**: VCN issuance (Step 9) CANNOT execute until Murabaha is signed (Step 7). Gateway middleware enforces HTTP 403 `MURABAHA_NOT_SIGNED`. Never skip this test in CI.

---

## 6 CORE MICROSERVICES

| Service | Owns | Key Deps |
|---|---|---|
| Gateway API | Auth, JWT, RBAC, rate limit, hard gates, routing | Redis, PostgreSQL |
| Product Service | URL pipeline, extraction waterfall, UPO | Rye API, BrightData, Groq |
| Credit Engine | XGBoost scoring, velocity, fraud signals, limits | PG, Redis, NADRA, TASDEEQ |
| Payment Orchestrator | VCN lifecycle, Stripe, Safepay, JazzCash, Raast, reconciliation | Stripe, Safepay, JazzCash, Raast |
| Ledger Service | Double-entry, journal entries, installment scheduling, charity routing | PG, Redis pub/sub |
| Notification Service | SMS, WhatsApp, push, email — Urdu + English | Jazz SMS, Firebase, SendGrid |

---

## 3 SHARIAH RULES (DB-LEVEL ENFORCEMENT)

**Rule 1 — Late Fee Charity**: `fn_apply_late_fee()` trigger creates `late_fee_charity_allocations` record. Zero retained by platform.

**Rule 2 — Cost Price Disclosure**: `murabaha_contracts` table has NOT NULL on `cost_price`, `profit_amount`, `profit_rate_pct`. Cannot generate contract without all three.

**Rule 3 — Prohibited Categories**: Products classified before any offer. Blocked: alcohol, tobacco, gambling, adult content, weapons, interest-bearing instruments. Returns HTTP 422 `PROHIBITED_CATEGORY`. Logged to `prohibited_items_log` (immutable).

---

## SHARIAH CONTRACTS

**Wakalah**: Customer appoints SahulatKar as Wakeel (agent) to buy on their behalf. Signed via OTP.

**Murabaha**: SahulatKar sells product at cost + 4% profit (all disclosed). Installment schedule fixed at signing. No additional charges post-agreement. Late fees → charity only.

---

## 19 ORDER STATES

`url_submitted` → `extracting` → `extraction_failed` → `offer_presented` → `contracts_pending` → `contracts_signed` → `down_payment_pending` → `down_payment_received` → `vcn_issued` → `purchasing` → `purchase_failed` → `purchase_confirmed` → `delivery_pending` → `in_transit` → `delivered` → `completed` | `cancelled` | `refunded` | `disputed`

---

## CREDIT ENGINE — 7 LAYERS

```
Layer 1: Hard Block Rules          < 5ms   — Redis, zero DB
Layer 2: Velocity & Fraud Rules    < 20ms  — Redis sliding windows
Layer 3: Identity & Device Score   < 50ms  — KYC signals → 0-100
Layer 4: Alternative Data          < 200ms — JazzCash API, device signals
Layer 5: ML Credit Scoring         < 100ms — XGBoost + LightGBM ensemble
Layer 6: Order-Specific Overlay    < 30ms  — product category, merchant
Layer 7: Portfolio-Level Controls  < 10ms  — concentration limits
TOTAL SLA: < 3 seconds
```

**Credit Bands**: A (PKR 25K, 25% down) | B (PKR 10K, 25%) | C (PKR 5K, 30%) | D (PKR 3K, 33%) | F (decline)

---

## URL EXTRACTION WATERFALL

```
Tier 1: Rye API        → Shopify/Amazon        < 5s    $0.02/fetch
Tier 2: JSON-LD        → schema.org parse       < 2s    free
Tier 3: Playwright+LLM → any website            < 60s   $0.05-0.15 proxy
Tier 4: HITL           → manual fallback        < 15min
```

---

## KEY DATABASE DESIGN RULES

- All monetary: `DECIMAL(14,2)` — never FLOAT
- All entities: `BIGSERIAL` internal PK + `UUID` external
- Soft deletes: `deleted_at TIMESTAMP` on all customer-facing tables
- Audit: AFTER INSERT/UPDATE/DELETE triggers on 30 sensitive tables → `audit_trails`
- Encryption: pgcrypto AES-256 for CNIC, IBANs, VCN details, MFA secrets
- Connection pool: PgBouncer transaction-mode (2000 client → 180 PG)
- Partitioning: `orders` and `payment_transactions` quarterly, `audit_trails` monthly



## MODULE INDEX → see /modules/

- [M01-auth.md](modules/M01-auth.md) — Auth & Identity Core
- [M02-kyc.md](modules/M02-kyc.md) — KYC & NADRA Integration
- [M03-url-pipeline.md](modules/M03-url-pipeline.md) — URL Pipeline & Product Service
- [M04-credit-engine.md](modules/M04-credit-engine.md) — Credit Engine & Risk Scoring
- [M05-contracts.md](modules/M05-contracts.md) — Shariah Contracts (Wakalah + Murabaha)
- [M06-payments.md](modules/M06-payments.md) — Payment Orchestrator
- [M07-vcn.md](modules/M07-vcn.md) — VCN Issuance & Management
- [M08-checkout-agent.md](modules/M08-checkout-agent.md) — Checkout Agent (Playwright)
- [M09-hitl.md](modules/M09-hitl.md) — HITL Queue & Ops Dashboard
- [M10-delivery.md](modules/M10-delivery.md) — Delivery & Tracking Service
- [M11-ledger.md](modules/M11-ledger.md) — Ledger & Installment Engine
- [M12-admin.md](modules/M12-admin.md) — Admin Dashboard (20 Modules)

## FEATURE SPECS → see /specs/

## DESIGN KIT → see DESIGN_KIT.md

---

## UNIT ECONOMICS (PKR 10,000 order)

| Item | PKR |
|---|---|
| Murabaha Fee (4%) | +400 |
| Interchange (~1.5%) | +150 |
| **TOTAL REVENUE** | **+550** |
| Safepay (down payment) | -106 |
| JazzCash (3 installments) | -156 |
| Rye API | -21 |
| Stripe VCN | -28 |
| SMS + AfterShip + Infra | -26 |
| **TOTAL COSTS** | **-337** |
| **NET CONTRIBUTION** | **+213** |
| Break-even default rate | ~1.9% |

---

## REGULATORY

| Body | Requirement |
|---|---|
| SECP | NBFC license / Regulatory Sandbox |
| SBP | Monthly RCD-1 report, AML/CFT |
| FMU | STR within 7 days, CTR auto-detect |
| NADRA | CNIC verification backbone |
| TASDEEQ | Credit bureau reporting mandatory |
| PECA 2016 | Data residency Pakistan, OTP e-signatures |
| Shariah Board | Quarterly audit, annual contract certification |

---

## INTEGRATION CONTRACTS (KEY)

**product.extracted** (Redis pub/sub):
```json
{ "event": "product.extracted", "order_id": "uuid",
  "upo": { "product_id": "uuid", "title": "str", "price_pkr": 0.00,
            "canonical_url": "str", "selected_variant": {}, "availability": "in_stock" } }
```

**payment.down_payment_confirmed** (Redis pub/sub):
```json
{ "event": "payment.down_payment_confirmed", "order_id": "uuid",
  "installment_id": "uuid", "amount_pkr": 0.00,
  "vcn_id": "str", "vcn_pan": "str", "vcn_expiry": "MM/YY", "vcn_cvv": "str" }
```

**order.purchase_confirmed** (Redis pub/sub):
```json
{ "event": "order.purchase_confirmed", "order_id": "uuid",
  "merchant_order_id": "str", "total_charged_pkr": 0.00,
  "confirmation_screenshot_s3": "s3://...", "timestamp": "ISO8601" }
```

**GET /credit/check** (REST, < 3s):
```json
{ "approved": true, "risk_band": "B", "approved_limit": 10000,
  "down_payment_pct": 25, "rejection_reason": null }
```

**POST /vcn/issue** — requires `order.status == "contracts_signed"` else HTTP 403.
