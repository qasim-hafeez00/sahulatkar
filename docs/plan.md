# SahulatKar — Production Implementation Plan (Backend & Platform)

> **Scope:** Backend microservices, shared libraries, database, async workers, integrations, security, observability, CI/CD, and runtime infrastructure.  
> **Out of scope for this document:** Customer and admin **frontend UI** (Next.js apps); you will add screens later. API contracts and OpenAPI exposure remain in scope so the UI can bind cleanly later.  
> **References:** `MASTER_PLAN.md`, `MASTER_PLAN_DETAILED.md`, `System-md-files/*.md`, and repository audit findings.

**Document version:** 1.0  
**Last updated:** 2026-04-12

---

## 1. Goals and production definition

### 1.1 What “production level” means here

| Dimension | Target |
|-----------|--------|
| **Correctness** | Business rules match specs (Shariah gates, order state machine, prohibited categories, late-fee charity routing). |
| **Data integrity** | Single Alembic chain; reversible migrations; `DECIMAL(14,2)` for money; no duplicate/conflicting migrations. |
| **Security** | AuthN/AuthZ on public APIs; service-to-service auth for internal routes; secrets in vault; PII encryption; webhook HMAC; CORS restricted by env. |
| **Reliability** | Health checks; idempotent webhooks; retries with backoff; dead-letter handling; distributed locks where needed. |
| **Observability** | Structured logs with `request_id`; metrics (RED/USE); tracing across services; alerts on SLO breaches. |
| **Operability** | Runbooks; migration playbook; feature flags; staging that mirrors prod topology. |

### 1.2 Non-negotiables (from product specs)

1. **Hard gate:** No VCN issuance unless **Murabaha signed** (`contracts_signed`) — enforced in **Gateway** (customer path) and **Payment Orchestrator** (internal path), with **automated tests** that cannot be skipped.  
2. **Money:** No floats in persistence; disclosed **cost / profit / rate** on Murabaha records.  
3. **Late fees:** **100%** charity routing — enforced in **ledger** logic and reconciled in reports.  
4. **Prohibited categories:** Block before financing offer; **immutable** audit of blocks.  
5. **Data residency:** Deploy and store regulated data in **ap-south-1** (or policy-approved region).

---

## 2. Current state (summary)

Use this as the baseline; update as work completes.

| Area | Status |
|------|--------|
| Six Python services + shared package | Substantial code; uneven depth. |
| Alembic | Revisions `001`–`011` exist; **duplicate `CREATE TABLE` risk** between M04/M06/M07 must be **resolved** before any production deploy. |
| `sk-shared` packaging | `readme = "README.md"` without file — **fix** for clean installs/CI. |
| Gateway ↔ orchestrator | VCN path **not fully wired** (Gateway may return `queued` without calling orchestrator). |
| K8s manifests in repo | **Missing**; CI/CD assumes deploy targets exist. |
| Ledger | **No automated tests** in repo today. |
| Frontends | **Deferred** — APIs must still be stable and documented. |

---

## 3. Implementation strategy

### 3.1 Phasing overview

```
Phase A — Foundation fix (blockers)
Phase B — Data & domain completeness (DB, models, triggers, seeds)
Phase C — Service hardening (per module M01–M12 backend)
Phase D — Integrations (payments, VCN, KYC, delivery, bureau)
Phase E — Async workers & queues (BullMQ/redis queues, idempotency)
Phase F — Platform (API gateway behavior, internal auth, rate limits)
Phase G — Observability & SRE (logs, metrics, traces, alerts)
Phase H — CI/CD & environments (staging/prod parity, smoke tests)
Phase I — Security & compliance (review, pen-test prep, documentation)
```

Phases **overlap** where safe (e.g. observability starts in C).

### 3.2 Dependency order (logical)

1. Fix **migrations + packaging** (Phase A).  
2. Align **SQLAlchemy models** with **single source of truth** schema.  
3. Implement **internal service contracts** (HTTP + Redis events) with **versioned payloads**.  
4. Harden **Gateway** as the only public entry (except health/internal LB).  
5. Fill **integration** adapters behind interfaces (mock → sandbox → prod).  
6. **Load and chaos** testing before prod cutover.

---

## 4. Phase A — Foundation fix (P0)

### A.1 Alembic migration repair

**Problem:** Overlapping definitions (`merchants`, `products`, `orders`, etc.) across `004`, `006`, `007` break **fresh** `alembic upgrade head`.

**Approach (choose one; document decision in ADR):**

- **Option 1 (recommended for early stage):** **Squash** migrations into a clean baseline (`001_baseline`) after freezing current model set; reset non-prod DBs; keep upgrade path documented for any existing staging DBs.  
- **Option 2:** **Rewrite** `006`/`007` to **alter** existing tables instead of `create_table` for objects already created in `004`/`005`, and add **data migration** steps if column renames differ.

**Deliverables:**

- [ ] Single linear upgrade from empty DB to `head` on PostgreSQL 16 + Timescale.  
- [ ] `downgrade` tested for one step and for baseline (as per policy).  
- [ ] CI: `alembic -c db/migrations/alembic.ini upgrade head` (fix path if currently wrong).

**Acceptance:** Fresh CI Postgres job runs migrations without error; **repeatable** locally via `docker compose` + `alembic`.

### A.2 Packaging

- [ ] Add `packages/shared-python/README.md` **or** remove `readme` from `pyproject.toml`.  
- [ ] Ensure every `apps/*/pyproject.toml` installs cleanly with `pip install -e` on **Python 3.12** (CI version).

### A.3 CI/CD alignment

- [ ] Migration job uses explicit **`-c db/migrations/alembic.ini`**.  
- [ ] Document required env vars for tests (`DATABASE_URL`, `REDIS_URL`).  
- [ ] Gate merge on: **ruff**, **mypy** (policy per service), **pytest** + coverage floor, **migration check**, **hard-gate tests**.

---

## 5. Phase B — Data & domain completeness

### B.1 Schema gaps vs `MASTER_PLAN_DETAILED`

Implement missing pieces **only if** still required by product:

- [ ] **`orders` partitioning** (if retained): migration + application queries.  
- [ ] **`audit_trails`** (and triggers) — append-only audit for sensitive tables.  
- [ ] **`system_settings` / `feature_flags` / `api_keys`** — if not covered by `011`.  
- [ ] **DB triggers:** `fn_apply_late_fee`, `fn_recalculate_available_credit` — **spec-compliant** charity routing.  
- [ ] **Indexes** (partial, GIN, composite) per performance plan.  
- [ ] **Seed migration** or **script:** roles, permissions, prohibited categories, chart of accounts, couriers.

**Acceptance:** Finance and compliance can produce **Shariah report** and **P&L** from real journal data in staging.

### B.2 Model alignment

- [ ] `sk_shared.models` matches migrations **1:1** for all exported tables.  
- [ ] Add missing **audit/system** models if tables exist.  
- [ ] Enforce **soft delete** conventions where specified.

---

## 6. Phase C — Module-by-module backend plan (M01–M12)

Each module lists **production** deliverables. APIs are **REST JSON** under `/api/v1` unless noted.

### M01 — Auth & identity

**Deliverables**

- [ ] Phone **E.164** validation; OTP hash in Redis; attempt limits; lockout.  
- [ ] JWT **RS256**; key rotation procedure; short-lived access + refresh with rotation.  
- [ ] **Admin** login: password + **TOTP** mandatory; optional IP allowlist per role.  
- [ ] **RBAC:** roles/permissions in DB; decorators/dependencies on **all** admin routes.  
- [ ] Session revocation; logout; concurrent session policy.  
- [ ] Rate limiting on `/auth/*` (Redis sliding window).

**Tests:** unit + integration (happy, abuse, token expiry, RBAC denial).

**Production:** Rate limits tuned; secrets from AWS Secrets Manager (or equivalent).

---

### M02 — KYC & NADRA

**Deliverables**

- [ ] **S3 presigned** uploads; server never stores raw bytes in DB.  
- [ ] **Shufti Pro** (or chosen vendor) **real** client: OCR, liveness, webhooks.  
- [ ] **NADRA Verisys** **real** client with **circuit breaker** and **retry**; 30-day cache in Redis as per spec.  
- [ ] **Manual review queue** + admin decision API; SLA fields; audit trail.  
- [ ] PII encryption at rest; retention policy (7-year NADRA JSON).

**Tests:** contract tests against vendor sandboxes; webhook signature verification.

**Production:** Vendor failover playbook; queue depth alerts.

---

### M03 — URL pipeline & product service

**Deliverables**

- [ ] URL normalize → platform detect → **waterfall** (Rye → JSON-LD → Playwright+LLM → HITL escalation).  
- [ ] **UPO** schema validation; persist `scraping_jobs`; polling API.  
- [ ] **Prohibited** classifier + **immutable** `prohibited_item_logs`.  
- [ ] **Murabaha pricing** service (plan types, rounding rules) — **disclosed** totals.  
- [ ] Merchant registry + **scrape_config** overrides.

**Tests:** golden URLs per platform; prohibited cases; job failure/retry.

**Production:** Proxy pool health; cost controls per tier; HITL queue integration.

---

### M04 — Credit engine

**Deliverables**

- [ ] All **7 layers** implemented with **bounded latency**; **timeouts** per layer.  
- [ ] **XGBoost** (or agreed model) artifact versioning; load from object storage; **no** unversioned pickle in prod.  
- [ ] **Velocity** + **blacklist** Redis keys; TTLs per spec.  
- [ ] **Portfolio** caps; **cold-start** caps per band.  
- [ ] **Explainability** endpoint for declines (SHAP or equivalent) for SECP-facing narrative.  
- [ ] **Admin:** limit adjust, blacklist, fraud alerts.

**Tests:** pipeline integration tests; SLA assertion (p99 &lt; 3s under load budget).

**Production:** Model rollout (champion/challenger) feature flags.

---

### M05 — Contracts (Wakalah + Murabaha)

**Deliverables**

- [ ] **ReportLab** (or template) PDF generation; **versioned** templates; SSB certification reference fields.  
- [ ] **Hash** stored; PDF in S3 encrypted.  
- [ ] OTP signing for both contracts; **confirmation** checkbox on Murabaha.  
- [ ] Order state transitions: `contracts_pending` → **`contracts_signed`** only after Murabaha signed.  
- [ ] **Hard gate** tests: **cannot** issue VCN before `contracts_signed`.

**Tests:** legal text hash regression optional; state machine tests mandatory.

---

### M06 — Payment orchestrator

**Deliverables**

- [ ] **Down payment** initiation per method (Safepay redirect, JazzCash/EP direct).  
- [ ] **Webhooks:** HMAC verification, **idempotency** keys, dedup store.  
- [ ] **Installment** schedule creation tied to **loan**; retry schedule.  
- [ ] **Manual payment** recording (admin) with audit.  
- [ ] **Reconciliation** job: match gateway files to `payment_transactions`.

**Tests:** webhook replay; duplicate event; partial failure recovery.

---

### M07 — VCN

**Deliverables**

- [ ] **Stripe Issuing** (or Lithic) **production** issuer; **MCC** and amount controls; single-use behavior.  
- [ ] PAN/CVV **encryption**; never log full PAN/CVV.  
- [ ] **Issue only if** Murabaha signed + business rules (down payment received per policy).  
- [ ] **Internal API** secured (mTLS or signed service JWT + network policy).  
- [ ] Emit **`vcn.issued`** event for downstream agent.

**Gateway wiring**

- [ ] Gateway **either** proxies to orchestrator **or** returns orchestrator response; **no** “fake queued” in production config.  
- [ ] Document **single** customer-facing contract for VCN issue.

**Tests:** E2E from signed contract → down payment (sandbox) → VCN → void.

---

### M08 — Checkout agent (product service)

**Deliverables**

- [ ] Playwright workers with **stealth** + **proxy** configuration.  
- [ ] Job queue consumer; **priority**; **DLQ** for failures.  
- [ ] **Self-healing** path with VLM (feature-flagged); cost caps.  
- [ ] Capture **merchant order id**, screenshots to S3; **purchase_executions** status.  
- [ ] Stripe charge confirmation correlates with VCN.

**Tests:** smoke against merchant **sandbox**; failure escalates to HITL.

**Production:** KEDA/HPA policies; dedicated node pool for Playwright (as per infra plan).

---

### M09 — HITL

**Deliverables**

- [ ] Queue **priority**, **claim**, **resolve**; **SLA** deadline field.  
- [ ] Optional **browser session** handoff (architecture decision: separate tool vs embedded).  
- [ ] Links to **order**, **execution**, **screenshots**.

**Tests:** concurrency (no double claim); resolution side effects (refund vs complete).

---

### M10 — Delivery & tracking

**Deliverables**

- [ ] **AfterShip** (or chosen) tracking create + webhook; **HMAC** verification.  
- [ ] Map statuses → internal order/shipment states; **Redis** events to Gateway/notifications.  
- [ ] **Timescale** retention for `tracking_events` as designed.

**Tests:** webhook fixtures; status mapping table tested.

---

### M11 — Ledger & billing

**Deliverables**

- [ ] **Double-entry** posting service; **balanced** journal validation.  
- [ ] **Daily billing sweep** (due installments); **retry** worker.  
- [ ] **Late fee** calculation → **charity** allocation workflow; **disbursement** reconciliation.  
- [ ] **TASDEEQ** reporting job (payloads per SBP rules) — interface + stub → prod adapter.  
- [ ] Admin finance APIs: P&L, reconciliation import, Shariah report.

**Tests:** **critical gap to close** — journal balance, charity routing, sweep edge cases.

---

### M12 — Admin & operations (backend only)

**Deliverables**

- [ ] All **admin** APIs implied by `M10-M12` spec: dashboard aggregates, user search, orders, risk queues, finance, audit export.  
- [ ] **Read replicas** for heavy reports (optional Phase 2 scale).  
- [ ] **Export** limits and **PII** masking per role.

**Note:** **UI deferred**; deliver **OpenAPI** + stable JSON schemas for future admin app.

---

## 7. Phase D — External integrations (matrix)

| Integration | Purpose | Milestone |
|-------------|---------|-----------|
| Jazz SMS / OTP | Customer OTP | M01 |
| Shufti / uqudo | KYC | M02 |
| NADRA Verisys | CNIC | M02 |
| S3 (KMS SSE) | KYC, PDFs, screenshots | M02–M08 |
| Rye / scraping | Product extraction | M03 |
| BrightData / proxy | Scraping | M03–M08 |
| OpenAI / Groq | Vision / LLM | M03–M08 |
| JazzCash / EasyPaisa / Safepay | Payments | M06 |
| Stripe Issuing | VCN | M07 |
| AfterShip | Tracking | M10 |
| TASDEEQ | Bureau | M11 |

**Each integration:** `interface` in code + **mock** + **sandbox** + **prod** implementation; feature flags control rollout.

---

## 8. Phase E — Events, queues, idempotency

**Deliverables**

- [ ] Standard **event envelope** (`sk_shared.events`) used everywhere; **correlation_id** propagation.  
- [ ] Redis pub/sub **or** move to **Redis Streams / SQS** if scale requires (decision record).  
- [ ] **Idempotency** keys for: webhooks, VCN issue, billing posts, notifications.  
- [ ] **Outbox pattern** (optional) for critical financial side effects.

**Acceptance:** Replay of events does not double-charge or double-post.

---

## 9. Phase F — API platform & Gateway

**Deliverables**

- [ ] **Single public base URL** → Gateway only.  
- [ ] **CORS** allowlist from env (no `*` in production).  
- [ ] **Request ID** middleware; unified error schema (`MASTER_PLAN_DETAILED` error registry).  
- [ ] **Rate limits** per route class; stricter on auth and webhooks.  
- [ ] **Internal** routes on orchestrator/ledger: **network policy** + **service auth**.  
- [ ] **OpenAPI** export aggregated or per-service for **UI later**.

---

## 10. Phase G — Observability

**Deliverables**

- [ ] **Structured JSON** logs; no secrets/PII; PAN/CVV masked.  
- [ ] **Prometheus** metrics per service: `http_*`, credit latency, queue depth, DB pool, Redis.  
- [ ] **OpenTelemetry** traces across Gateway → internal services (W3C trace context).  
- [ ] **Dashboards:** credit, payments, queues, errors.  
- [ ] **Alerts:** P1 payment webhook failures, P2 credit SLA breach, DB pool saturation.

---

## 11. Phase H — CI/CD & environments

**Deliverables**

- [ ] **Dockerfiles** non-root, multi-stage, scanned in CI.  
- [ ] **Build** only changed services (paths-filter / turborepo-style).  
- [ ] **Staging** deploy with **smoke tests** (`tests/smoke` expanded beyond health).  
- [ ] **Production** manual approval; **rollback** procedure (image tag revert).  
- [ ] **K8s** manifests in repo: Deployments, Services, HPA/KEDA, ConfigMaps, **ExternalSecrets**, Ingress, **NetworkPolicies**.  
- [ ] **Terraform:** VPC, EKS, RDS, ElastiCache, S3, IAM, ECR — **state** in S3 backend.

---

## 12. Phase I — Security & compliance

**Deliverables**

- [ ] **Secrets** rotation runbook; no secrets in git.  
- [ ] **Encryption:** RDS, S3, Redis in transit; application-level for CNIC/IBAN/VCN.  
- [ ] **Webhook** signing on all external callbacks.  
- [ ] **OWASP** API review; **dependency** scanning (Dependabot/Snyk).  
- [ ] **PECA / SECP / SBP** documentation pack: data flow, retention, audit, incident response.  
- [ ] **Penetration test** before public launch.

---

## 13. Milestone schedule (suggested)

| Milestone | Content | Exit criteria |
|-----------|---------|----------------|
| **M0** | Phase A complete | Clean migrations, CI green on Python 3.12 |
| **M1** | M01–M03 + infra skeleton | Register → KYC stub → extract URL in staging |
| **M2** | M04–M05 | Credit + signed contracts with hard gate |
| **M3** | M06–M07 | Real sandbox payments + VCN sandbox |
| **M4** | M08–M09 | Automated checkout path + HITL fallback |
| **M5** | M10–M11 | Tracking + ledger + billing sweep |
| **M6** | Phase G–H | Observability + full staging on EKS |
| **M7** | Phase I + load test | Production go/no-go |

Adjust dates with your team capacity; keep **M0** as the **first** time-bound goal.

---

## 14. Frontend (explicitly deferred)

When you add UI later:

- Consume **documented OpenAPI** contracts.  
- Implement **US-01–US-20** and **AD-01–AD-28** against the same Gateway; no duplicate business logic in the browser.  
- This plan assumes **no** backend changes required for basic CRUD beyond what’s listed above.

---

## 15. Living document

- Update this file when milestones complete or scope changes.  
- Add **ADR**s (`docs/adr/`) for: migration squash, event bus choice, VCN provider, checkout agent scaling.

---

**End of plan**
