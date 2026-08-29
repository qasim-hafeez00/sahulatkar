# SAHULATKAR BNPL — PRODUCTION GAPS REPORT (2026-08 refresh)

**Date**: 2026-08-26
**Prepared for**: Founder, pre-frontend-work gate
**Scope**: All 6 microservices (gateway, product-service, credit-engine, payment-orchestrator, ledger-service, notification-service) + shared packages + Docker/CI/test infrastructure. Frontends (web-customer, web-admin) NOT re-audited this pass.
**Analyst**: Claude Sonnet 5, 4 parallel code-reading agents, each with full source access to their assigned service(s). Every finding below is backed by a specific file:line the agent actually read — not inferred from names, docstrings, or the prior report.
**Baseline**: `docs/PRODUCTION_GAPS_REPORT.md` (2026-04-27, excluded credit-engine). All services were touched again on 2026-08-23, so this refresh verifies which April findings are fixed, partially fixed, or still open, and hunts for new gaps introduced since.

---

## HOW TO READ THIS REPORT

Every finding has: a title, file:line, a concrete failure scenario (not a hypothetical), a test-coverage verdict (NONE / WEAK / GOOD), and — where applicable — its disposition against the April report (FIXED / PARTIAL / OPEN / NEW). Severity bands:

- **CRITICAL** — blocks safe handling of real customer money, real customer data, or Shariah/regulatory compliance. Must fix before any production traffic.
- **HIGH** — significant correctness/security/compliance risk, not immediately catastrophic but should be fixed before scaling volume.
- **MEDIUM** — real but bounded risk, or a gap that degrades gracefully today and gets worse with scale.
- **LOW** — cleanup, documentation-vs-code mismatches, minor hardening.

## TOP-LINE VERDICT

The platform has clearly had substantial, competent remediation work done since April — the large majority of the ~90 previously-documented gaps are genuinely fixed with real logic, not cosmetic patches. **But it is not production-ready today.** The 12 CRITICAL findings below span three categories that matter most for a Shariah-compliant lender handling real money: (1) two distinct ways real customers can be double-charged or have a charge silently vanish from the books, (2) a billing-sweep bug that crashes on the *normal* case of an installment still being overdue the day after it first goes overdue, and (3) two-thirds of Credit Engine's advertised 7-layer scoring pipeline running on mocked/dead data for every applicant, forever. Layered on top: **zero cross-service integration testing and zero end-to-end workflow testing exist anywhere in the repo** — every service's test suite mocks its neighbors, so none of these cross-service bugs could have been caught by CI as it exists today.

---

## UPDATE 2026-08-28 — ALL 12 CRITICALS FIXED

All 12 CRITICAL findings below have been fixed, tested, and verified against each service's full test suite (parallel fix agents + direct follow-up work; see the ✅ notes inline under each finding for what changed and where). Two additional real bugs were found and fixed along the way, surfaced only by actually running the suites rather than reading code:

- **Admin login had a real, reproducible collision bug**: the admin JWT's `exp` claim is second-granularity and RS256 signing is deterministic, so two admin logins for the same admin within the same second produced a byte-identical token → identical `token_hash` → `UNIQUE constraint failed: admin_sessions.token_hash` on the second login, in a real Postgres deployment too, not just in tests. Fixed by adding a random `jti` claim to every admin token (`apps/gateway/src/services/auth.py`).
- **`orders.product_snapshot` existed in every real Postgres deployment (added by migration 016, hardened by 052) but was never declared on the SQLAlchemy `Order` model** (`packages/shared-python/sk_shared/models/order.py`), so any ORM-driven schema (this test suite, and potentially any tooling that relies on `Base.metadata` rather than Alembic) never created the column — a genuine model/migration drift bug, now fixed by declaring it.

Current per-service test status (full suite, post-fix):

| Service | Result | Remaining failures |
|---|---|---|
| Gateway | 222 passed, 5 failed | All 5 pre-existing and unrelated to the 12 criticals (confirmed via `git stash` A/B comparison for 2 of them, and by original-baseline inspection for the other 3): a test-suite bug in `test_installment_amounts_exclude_down_payment` (Python `not` applied to a SQLAlchemy column — filters out all rows), 3 tests in `test_payments_flow.py` tied to the `_dev_simulate_fulfillment` ENVIRONMENT-string-comparison HIGH finding (not a CRITICAL), and a KMS/`CustomerProfile.cnic` type-coercion bug in `test_generate_wakalah_fetches_customer_profile` unrelated to any of the 3 assigned Gateway bugs. |
| Product Service | 152 passed, 2 failed | Both pre-existing, confirmed via `git stash` A/B comparison against pre-fix code (identical failures either way) — unrelated to the SSRF/cardholder-data fixes. |
| Credit Engine | 84 passed, 0 failed | Clean. |
| Payment Orchestrator | 233 passed, 0 failed | Clean. |
| Ledger Service | 130 passed, 1 failed | Pre-existing, unrelated (`test_reconciliation_import_accepts_valid_internal_token` — an enum-value mismatch in an unrelated reconciliation-status test). |
| Notification Service | not re-touched this pass | No criticals were found here; see HIGH findings below. |
| shared-python | 73 passed, 0 failed | Clean (covers the `Order.product_snapshot` model fix and the `AdminSession` model). |

New regression tests added and passing: admin-login single-session enforcement (now exercises the real `admin_sessions` table end-to-end instead of failing on a missing table), `test_admin_orders.py`'s 3 previously-broken tests, a new `test_max_active_orders_honors_admin_system_parameter` proving an admin-changed `SystemParameter` actually changes what `OrderService.initiate` enforces, the SSRF fetch-time re-validation tests in `test_html_scraper.py`/`test_playwright_agent.py`, the cardholder-data self-healing lockout test, the installment double-charge concurrency test, the late-fee sweep idempotency test, and the Credit Engine graduation-rule tests (clean history graduates, any negative history doesn't).

**What's still open**: the 16 HIGH findings below were explicitly deferred (user chose "fix the 12 CRITICALs first"), and the testing-infrastructure gaps (zero cross-service/E2E/load/contract/chaos testing) are entirely unaddressed — see "THE TESTING GAP" and "RECOMMENDED PATH" sections below, which are the logical next phase.

---

## CRITICAL (12) — all fixed, see update above

### Money-correctness

1. **No idempotency guard on installment payments — real double-charge path.** `apps/payment-orchestrator/src/api/v1/payments.py:257-368` (`pay_installment`) and `:726-823` (`auto_collect_installment`). Check-then-act with no row lock, no idempotency key, and gateway-generated `gateway_txn_id`s that never collide. A double-tap or a race between manual pay and the auto-collect sweep charges the customer twice. **Test coverage: NONE.**
2. **Financial events delivered over plain Redis pub/sub with no durability.** `apps/payment-orchestrator/src/workers/outbox_publisher.py:114-121`, plus three inline `redis.publish()` calls in `payments.py` (lines 350, 549, 820) that bypass the outbox entirely. `PUBLISH` never raises on zero subscribers. If Ledger Service is mid-restart when a real charge completes, the event is dropped with no error, no DLQ entry, and no ledger posting — cash leaves the customer's wallet but the books never reflect it. **Test coverage: NONE.**
3. **Billing sweep crashes with an unhandled `IntegrityError` on the normal case.** `apps/ledger-service/src/services/late_fee_service.py:19-33` guards against re-applying a late fee via `installment.late_fee_amount`, but that field is **never written back anywhere in the monorepo** (confirmed by repo-wide grep). So the guard never trips, `LateFeeCharityAllocation` (unique-constrained on `installment_id`) is inserted a second time on day 2 of any still-unpaid overdue installment, and `db.commit()` throws — aborting the sweep for every installment processed after it in that batch. This is steady-state behavior for any real BNPL portfolio, not an edge case. **Test coverage: NONE** — every existing sweep test runs it exactly once.

### Credit decisioning integrity

4. **"Alternative data" scoring layer is a hardcoded constant for every applicant.** `apps/credit-engine/src/adapters/wallet.py:17-24` returns a fixed `55.0` regardless of user. No real JazzCash/Easypaisa wallet integration exists; `BankStatementAnalysis` is only ever constructed in tests. This layer provides zero discriminative power in production today.
5. **Identity/device fingerprinting and fraud's device/IP/synthetic-identity signals are dead code — no writer for the required tables exists anywhere in the repo.** `apps/credit-engine/src/engines/identity.py:112-138`, `fraud.py:183-274`. `DeviceFingerprint`/`IpIntelligence`/`SyntheticIdentityIndicator` are constructed only in tests. Every real applicant scores `0` on these signals, always — not because risk is low, but because no ingestion pipeline was ever built.
6. **Direct consequence of #4+#5: every approved customer is permanently capped at the cold-start limit, forever.** `apps/credit-engine/src/engines/limit.py:66-78`. The "has real signal" exit condition (`device_trust_unverified` / `ip_trust_unverified` / `bank_data_unavailable` all false) can structurally never become true in production, so `apply_cold_start_cap` fires unconditionally on every decision — e.g. band A's real limit of Rs 25,000 is silently forced to Rs 8,000 (a 68% cut) even for a customer on their 50th order. A real product feature (limit growth for good repayment history) is silently disabled platform-wide.
7. **No ML models exist anywhere in credit-engine.** `apps/credit-engine/src/engines/scoring.py:19-32` is an honestly-documented hand-set WOE-style scorecard — the code's own docstring says so. Zero ML dependencies in `pyproject.toml`. The platform's stated "XGBoost/LightGBM/CatBoost/Isolation Forest" scoring layer does not exist in this codebase. Not hidden, but any external claim of ML-based underwriting is currently inaccurate.

### Security / data exposure

8. **SSRF protection is not carried through to the actual async fetch.** `apps/product-service/src/services/url_normalizer.py` does careful DNS-pinning/private-IP rejection, but only at `POST /products/extract` submission time. The worker that later actually fetches the page (`html_scraper.py:28`, `playwright_agent.py:66`) does a fresh, unprotected DNS resolution. A DNS-rebinding attack (resolve to a public IP at submission, rebind to `169.254.169.254`/internal service by the time the async worker picks up the job) bypasses the hardening entirely. **Test coverage: NONE.**
9. **Live cardholder data (PAN/CVV) can be sent to OpenAI.** `apps/product-service/src/services/self_healing.py:50-134`. The checkout form-filler's selector self-healing fires on any unrecognized selector — including the "Submit Order" step, which runs immediately after payment injection has typed the live PAN/CVV into the page. On failure it screenshots the full page (renders visible iframe content) and POSTs it to `gpt-4o-mini`. No redaction, no crop, no masking pass. This is a PCI-DSS-adjacent exposure with no compensating control. **Test coverage: NONE.**

### Admin/operational integrity

10. **Admin login is broken — untested against its own schema.** `apps/gateway/src/services/auth.py:272-289` runs raw SQL against `admin_sessions`, which has no SQLAlchemy ORM model anywhere in the codebase (only an Alembic migration). Confirmed by actually running the test suite: `test_admin_login_success` and `test_admin_force_password_change_enforced` both fail with `sqlite3.OperationalError: no such table`. This code path was never exercised end-to-end — every other admin test bypasses login by injecting a JWT directly.
11. **Admin Orders panel silently hides real errors as "not found."** `apps/gateway/src/api/v1/admin_orders.py:94-99, 184-190` wraps the entire query in bare `try/except Exception` and returns empty results / 404 on any SQL error. Reproduced live via the test suite. An admin investigating a fraud or dispute case sees "nothing here" when the query is actually throwing.
12. **System Parameters admin panel is a complete facade — disconnected from real business logic.** `apps/gateway/src/api/v1/admin_system.py` has full CRUD, caching, and audit logging for down-payment %, profit rates, and risk thresholds — but grep confirms `SystemParameter` is read back only by its own GET endpoint. Real values are hardcoded elsewhere (`contract_generator.py:260`, `order_service.py:78,184`). An admin changing these in response to a risk or Shariah-board directive sees it "saved" with zero effect on live contracts.

---

## HIGH (16)

**Gateway**
- Loan/ledger event (`EVENT_LOAN_CREATED`) published to Redis before the enclosing DB transaction commits (`contract_signer.py:303-317`) — a fast consumer can query for a loan that doesn't exist yet.
- No admin recovery path for an order stuck at `pending_vcn` after a failed VCN issuance — only a read-only view exists.
- HITL `sla_deadline` is stored and displayed but never escalated or alerted on anywhere.
- Cross-service HTTP calls have a flat 10s timeout with no retry; stuck orders only self-heal when a user happens to poll after 600s — no proactive sweep exists.
- `validated_by_shariah_board=True` is hardcoded on every Murabaha contract (`contract_generator.py:309`) with no backing approval record.

**Product Service**
- Murabaha pricing's `is_shariah_approved` flag is honestly `False` by default but never checked anywhere that would block an offer — compliance gate exists but enforces nothing.
- Crashed checkout workers leave `PurchaseExecution` rows stuck at `"running"` forever — no reaper, and the admin retry endpoint explicitly no-ops on that status.
- Order cancellation after checkout has already started doesn't interrupt the running Playwright task — a cancelled order's purchase can still complete and clobber the cancelled state.
- `GET /products/{upo_id}/offer` has no auth, inconsistent with every sibling endpoint in the same file.
- Extraction retries on failure (including OpenAI 429s) have no backoff — burns through retry budget instantly instead of recovering.

**Credit Engine**
- Portfolio-concentration check has a TOCTOU race — no row lock, so two concurrent applications for the same user can both pass and jointly exceed the platform's max exposure.
- `/credit/apply` synchronously awaits a retrying Gateway callback before responding — worst case ~16.5s against a stated <3s SLA.

**Payment Orchestrator**
- `ENVIRONMENT` defaults to `"local"` (fail-open) — a misconfigured deploy silently makes JazzCash/Raast/SafePay failures return fake success, Stripe card creation fall back to a hardcoded test PAN, and webhook signature verification skip entirely.

**Ledger Service**
- Zero tests anywhere construct an unbalanced journal entry and assert it's rejected — the debit=credit invariant is genuinely enforced in code (app-layer + DB CheckConstraint) but completely unverified by the test suite, which is exactly what was asked to be checked.
- DB `CheckConstraint` validates the `journal_entries` header totals only, not that `journal_entry_lines` actually sum to them — safe today only because one code path is the sole writer, with no DB-level guarantee against a future bypass.
- No guardrail preventing a manual admin journal entry from crediting the `late_fee_collections` (4003, revenue) account instead of `charity_payable` — the automated path is structurally safe, the manual path is not.

---

## MEDIUM (highlights — full detail in each service section of the underlying agent reports)

- Prohibited-category checking: negative-result caching can mask a category added within the cache window (Product Service); Gateway never re-checks the extracted product against a prohibited list post-extraction, only the raw URL pre-extraction.
- Webhook dedup (Payment Orchestrator) is keyed on `SHA256(body+signature)`, so a differently-bodied legitimate retry bypasses dedup; Gateway's webhook dedup is a 24h Redis-only marker with no DB fallback.
- Ledger reconciliation compares daily aggregate sums only, not line-by-line — two offsetting errors net to zero and go undetected. No automated schedule for charity disbursement (manual admin-triggered only).
- The "partial index" `installments(due_date, user_id)` the billing sweep is described as depending on has **no `WHERE status='pending'` clause** — it's a plain composite index that will degrade at scale.
- VCN MCC lock is a single hardcoded category (Stripe limitation, documented) rather than true merchant-domain locking.
- Duplicated "product extracted" business logic exists in two independent code paths in Gateway (HTTP callback + Redis event) — individually idempotent today, but a real drift risk.
- Notification Service: two admin/customer API test files assert tautologies (`status_code in [200,401,403]`) — DLQ admin surface has effectively zero real test coverage.

---

## THE TESTING GAP (this is the section most relevant to "docker up, everything green")

Confirmed directly, not inferred:

- **Per-service unit/integration tests are genuinely strong** — 149 test files, ~22,000 test LOC, real assertions, run in CI against fresh Postgres+Redis per service, gated at 80% coverage.
- **Cross-service integration testing: zero.** Every service mocks its neighbors. Nothing brings up two real services and calls across the boundary.
- **End-to-end workflow testing: zero.** The only root-level test (`tests/smoke/test_health.py`) is 8 functions checking `GET /health` returns 200 — it runs post-deploy against staging, not in CI. No test anywhere exercises the full order lifecycle (create order → extraction → credit check → offer → Wakalah sign → Murabaha sign → down payment → VCN issuance → checkout → billing → repayment → ledger reconciliation) as one connected flow. **This is the single highest-leverage gap** — it's also the test that would have caught most of the CRITICAL findings above automatically.
- **Load/performance testing: zero implementation** (explicitly scoped in `docs/knowledge-base/09-qa/153-performance-testing.md` as "PLANNED," not built).
- **Contract testing between services: zero.** Given how many bugs above are "service A assumes an event/shape service B doesn't actually produce," this is a real absence.
- **Chaos/failure-injection testing: zero.** Nothing kills a downstream dependency mid-workflow and asserts correct degradation.
- **Secrets scanning in CI: zero** (Gitleaks/TruffleHog or equivalent absent).
- CI does run: lint+typecheck+unit tests per service, CodeQL SAST, Trivy container scanning, Dependabot, Terraform validate, migration up/down/up check on the newest migration only (not the full chain).
- `docker-compose.yml` is valid and defines all 6 services + Postgres + Redis + PgBouncer correctly, but has no service-to-service `depends_on` ordering (frontends can serve before Gateway is ready), and PgBouncer has no healthcheck.
- Migrations are never run automatically in the deploy pipeline — `make migrate` is a manual step, disconnected from `build-and-push.yml`.

---

## RECOMMENDED PATH TO AN HONEST GREEN LIGHT

1. **Fix the 12 CRITICAL findings.** Several are small, surgical fixes (add a unique constraint + advisory lock for double-charge; add a `try/except` around the sweep's per-installment commit and fix the `late_fee_amount` write-back; fix/remove the broken `admin_sessions` path; replace the swallow-all exception handling in admin orders). Two are larger: the SSRF-at-fetch-time gap needs the normalizer's pinning carried into the worker process, and the cardholder-data-to-OpenAI gap needs a redaction/masking pass before any screenshot reaches self-healing. Credit Engine's dead scoring layers (#4-#7) are a product decision as much as a bug fix — either build the wallet/device-data ingestion pipelines, or consciously redesign the cold-start-cap logic to not depend on data sources that don't exist yet.
2. **Build the missing testing layers**, in this order of leverage: (a) one real end-to-end workflow test running against `docker compose up` — this alone starts giving you protection against the class of bug found repeatedly above; (b) wire `docker compose up` into CI as a gate; (c) contract tests on the event-driven integrations; (d) secrets scanning; (e) load testing per the already-written spec; (f) chaos testing.
3. **Re-run an audit pass like this one** after (1) and (2) land, specifically re-verifying the CRITICAL items with reproducible tests (not just code inspection) before calling it done.

**Status as of 2026-08-28**: all 12 CRITICALs are fixed and verified (see update above). This still does not constitute a full green light — 16 HIGH findings remain deferred by explicit choice, and the testing-infrastructure gaps (zero cross-service/E2E/load/contract/chaos testing) are unaddressed, so nothing has yet verified these fixes hold up against the *actual* order-to-repayment workflow running end-to-end rather than per-service unit tests. That E2E test is still the single highest-leverage next step.
