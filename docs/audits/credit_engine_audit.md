# Credit Engine — Integration Reference

Rewritten 2026-08-28 as a direct-from-code reference, not a scored audit. Every claim below is
grounded in the current source under `apps/credit-engine/` (plus the parts of `apps/gateway/`
and `infra/k8s/` needed to establish who actually calls this service). This replaces an earlier
version of this file that described a `src/main.py`/`src/layers/*` structure that does not
exist in the current codebase and carried an invented "Production Readiness" score.

Full test suite as of this writing (`../../.venv/Scripts/python.exe -m pytest -q` from
`apps/credit-engine/`): **87 passed, 0 failed** (86s).

---

## 1. Service Purpose

Credit Engine is the underwriting/decisioning microservice for SahulatKar's BNPL platform: given
a user and an order, it runs a rule-based scoring pipeline and returns an approve/reject/
partial-approve/counter-offer decision, a risk band, a credit limit, and a required down-payment
percentage. It owns its own Postgres tables (`credit_applications`, `risk_assessments`,
`credit_feature_snapshots`, `credit_policy_versions`, `blacklisted_entities`,
`fraud_alerts`, `manual_review_queue`, `device_fingerprints`, `ip_intelligence`,
`synthetic_identity_indicators`) but also reads Gateway-owned tables (`users`, `loans`,
`installments`, `bank_statement_analysis`, `risk_blacklist`) directly against the same physical
database, and pushes finished decisions back into Gateway's `users` table via an authenticated
HTTP callback so Gateway's own read paths (`GET /api/v1/credit/status`) stay in sync without
calling this service live. It sits entirely inside the private network — see section 5.

## 2. API Endpoint Catalog

Base path: none (routes are mounted directly, e.g. `GET /credit/check`). Every route except
`/health` requires a bearer JWT signed with the same RS256 key Gateway issues
(`settings.JWT_PUBLIC_KEY`), decoded via `sk_shared.security.decode_access_token`. "Customer JWT"
below means the token must carry a `user_id` claim resolving to a live `users` row (`get_current_user`
in `src/core/dependencies.py`); "Admin JWT" means an `admin_id` claim resolving to a live
`admin_users` row (`get_current_admin`). **Credit-engine does no per-route permission/role check
of its own** — any authenticated admin can hit any `/admin/*` route here, unlike Gateway's RBAC
(`manage_risk`, etc.) which gates the equivalent Gateway-side admin actions.

Rate limits (`src/core/rate_limit.py`): the five decision-pipeline routes
(`/credit/check`, `/credit/evaluate`, `/credit/apply`, `/credit/prequalify`, `/credit/recalculate`)
are capped at 30 requests/60s per authenticated user (falls back to per-IP if the token doesn't
decode). Admin write routes (`/admin/credit/override`, `/admin/credit/adjust`,
`/admin/risk/blacklist`) are capped at 60/60s per admin. Read-only routes
(`/credit/score`, `/credit/history`, `/credit/status`, `/credit/me`, `/admin/risk/alerts`,
`/credit/explain/{id}`) are unlimited.

### Customer-facing (Customer JWT)

**`GET /credit/check`** — query params `order_amount: float (>0, required)`,
`product_category: str = "general"`, `is_first_order: bool = false`,
`device_fingerprint_hash: str | None`. Scoped to the caller (`current_user`, no `user_id` param).
Runs the full decision pipeline (section 3) but does **not** persist a `CreditApplication` — a
"what would happen" check, not a hard pull. Response (`CreditCheckResponse`): `approved: bool`,
`outcome: str`, `risk_band: str`, `approved_limit: float`, `down_payment_pct: float`,
`rejection_reason: str | None`, `manual_review_required: bool`, `requested_amount: float | None`,
`suggested_down_payment_pct: float | None`, `processing_time_ms: int`, `explanation: dict`.

**`POST /credit/evaluate`** — body `CreditEvaluateRequest {user_id, order_amount, product_category,
is_first_order, device_fingerprint_hash}`. Identical pipeline call to `/credit/check` (JSON body
instead of query string), still no `CreditApplication` written. `user_id` in the body must equal
the caller's own uuid or the request 403s (`_require_self`) — despite taking a `user_id` field
this is not a service-to-service "check anyone" endpoint. Same response shape as `/credit/check`.

**`POST /credit/apply`** — body `CreditApplyRequest {user_id, requested_limit (>0),
application_type: "onboarding"|"limit_increase"|"limit_review"|"manual_request"|"periodic_review"
= "manual_request", order_amount (>0), product_category, is_first_order,
device_fingerprint_hash}`. Optional `Idempotency-Key` header (scoped per-user; a concurrent
duplicate returns 409). Self-only, same as `/credit/evaluate`. Runs the full pipeline **and**
persists `CreditApplication` + `RiskAssessment` (+ `CreditFeatureSnapshot` if a decision was
reached) rows. On any approved outcome (`approved` or `partial_approval`, not
`increase_down_payment` or `rejected`), fires a background task that pushes the result to
Gateway's `/internal/users/{id}/credit-result` callback so `users.credit_limit` /
`available_credit` / `risk_band` reflect the new decision. Guarded against two race conditions
(both hold in current code — see section 4): a per-user Redis lock spanning the
portfolio-concentration check through the `CreditApplication` insert, and a `SELECT ... FOR
UPDATE` on the user's row inside that same check. Response (`CreditApplyResponse`):
`application_id: str`, `status: str`, `approved_limit: float | None`, `risk_band: str | None`,
`rejection_reason: str | None`, `manual_review_required: bool`, `outcome: str | None`,
`suggested_down_payment_pct: float | None`.

**`POST /credit/prequalify`** — body `{user_id, product_category}`. Self-only. A *soft* check:
eligibility (KYC/blacklist/category) + scoring + category overlay only — explicitly skips the
fraud/velocity check and the portfolio-concentration check that `/credit/apply` and
`/credit/check` run, and writes nothing (no `CreditApplication`, no fraud alert, no manual-review
entry). Meant for a checkout flow to show an indicative limit before the customer commits.
Response (`PrequalifyResponse`): `eligible: bool`, `reason: str | None`, `indicative_limit: float`,
`down_payment_pct: float | None`, `risk_band: str | None`, `processing_time_ms: int`.

**`GET /credit/score`** — no params. Current identity + affordability score with **no** eligibility
gate, **no** fraud check, and no application record — a pure "check your score" read, distinct
from a lending decision. Response (`CreditScoreResponse`): `user_id`, `risk_band: str`,
`score: float`, `identity_score: float`, `alt_data_score: float`, `model_version: str`.

**`GET /credit/history?limit=20 (1-100)`** — every `CreditApplication` row for the caller
(approvals and rejections both, with `rejection_reason`), most recent first. Response
(`CreditHistoryResponse`): `user_id`, `applications: [{application_id, application_type, status,
requested_limit, approved_limit, rejection_reason, decided_by, created_at}]`.

**`POST /credit/recalculate`** — no body. Re-runs identity + affordability + scoring against the
user's *current* data and reports the delta against their standing approved limit. **Read-only —
it proposes, it never applies.** Raising a live limit still requires an explicit admin override
(there is no automated "N on-time payments → limit increase" job wired up; see section 4).
Response (`RecalculateResponse`): `user_id`, `current_limit: float`, `recalculated_limit: float`,
`risk_band: str`, `limit_increased: bool`, `delta: float`.

**`GET /credit/status`** and **`GET /credit/me`** (identical alias) — no params. Response
(`CreditStatusResponse`): `user_id`, `current_limit: float` (max approved limit across
`CreditApplication` rows), `utilized_amount: float` (**hardcoded to `0.0`** — credit-engine does
not track drawn/repaid balance itself, see section 4), `available_limit: float`,
`assessments: [{assessed_at, risk_band, approved_limit, score}]` (last 10 `RiskAssessment` rows).

### Admin-facing (Admin JWT)

**`POST /admin/credit/override`** and **`POST /admin/credit/adjust`** (identical; `/adjust` is a
compatibility alias for older clients) — body `CreditOverrideRequest {user_id, new_limit (>0),
reason_code, notes?, admin_id = "system"}`. Bypasses the scoring pipeline entirely: writes a
`CreditLimitHistory` row and a `manual_override`-type `CreditApplication` set to the new limit,
pushes the result to Gateway **synchronously** (awaited inline, not backgrounded — this route has
no request-scoped `BackgroundTasks` the way `/credit/apply` does), and writes an audit-trail
event (`module="credit_admin", action="override_limit"`). Response (`CreditOverrideResponse`):
`status`, `user_id`, `new_limit`, `reason_code`.

**`GET /admin/risk/alerts?limit=20 (1-200)`** — latest `RiskAssessment` rows with `risk_band` in
`{E, F}`. Response (`RiskAlertsResponse`): `alerts: [{assessment_id, user_id, risk_band, score,
flags, created_at}]`.

**`POST /admin/risk/blacklist`** — body `BlacklistRequest {entity_type, entity_value, reason_code,
severity = "high", blacklisted_by = "system"}`. Dual-writes `BlacklistedEntity` (credit-engine's
own table) and `RiskBlacklist` (the table Gateway's own `/admin/risk/blacklist` UI reads/writes —
the two never synced before this dual-write, so a block placed through either surface is now
honored by both). If `entity_type == "user"`, also sets a 1h Redis cache flag so subsequent
`EligibilityEngine` checks short-circuit without a DB hit. Audit-logged. Response
(`BlacklistResponse`): `status`, `entity_type`, `entity_value`, `reason_code`, `severity`,
`active: bool`.

**`GET /credit/explain/{assessment_id}`** — note: lives under `/credit/`, not `/admin/credit/`,
but still requires an Admin JWT. Returns the persisted explanation blob for one `RiskAssessment`.
Response (`CreditExplanationResponse`): `assessment_id`, `found: bool`, `explanation: dict | None`
(see section 3's explanation shape), `flags: list[str]`, `model_version: str | None`.
Audit-logged.

### Unauthenticated

**`GET /health`** → `{"status": "ok", "service": "credit-engine"}`.

## 3. Scoring Pipeline / Business Logic

`CreditPipelineService.evaluate_credit` (`src/services/pipeline.py`) runs six engines in order,
each reading from one shared, versioned `RulePolicy` (`src/policy/rule_policy.py`, DB-backed via
`credit_policy_versions`, Redis-cached). This is the pipeline backing `/credit/check`,
`/credit/evaluate`, and `/credit/apply`; `/credit/prequalify` and `/credit/recalculate` run a
reduced subset (noted above).

1. **EligibilityEngine** (`src/engines/eligibility.py`) — hard blocks. Rejects immediately if: the
   product category is in `RulePolicy.prohibited_categories` (alcohol, tobacco, gambling, adult
   content, weapons, interest-bearing instruments, non-halal food); the user is blacklisted (checked
   against a Redis cache, `BlacklistedEntity`, *and* `RiskBlacklist` — three lookups because the
   two DB tables aren't the same one); the user's account `status` is `suspended`/`blocked`; or the
   user's latest KYC record isn't `APPROVED`. **No credit decision is possible before KYC is
   approved** — this is the correct thing for a frontend to gate on before ever calling
   `/credit/check`.
2. **FraudEngine** (`src/engines/fraud.py`) — velocity: rejects if more than 3 applications in 24h
   or more than 1 in the last hour (Redis sliding window, per-policy thresholds). Then a composite
   fraud score from device-fingerprint / IP-reputation / synthetic-identity signals (see section 4
   — these tables have no writer in production). Below `fraud_review_threshold` (40) the request
   proceeds untouched; between 40 and `fraud_block_threshold` (80) it proceeds but sets
   `manual_review_required=true` and raises a `FraudAlert` + `manual_review_queue` entry; at/above
   80 it's a hard reject.
3. **IdentityEngine** (`src/engines/identity.py`) — 0-100 trust score from KYC approval (30 pts) +
   NADRA confidence (20) + Shufti face-match (20) + liveness (10) + account tenure (5) + verified
   device/IP trust (up to 15, only awarded if a real clean `DeviceFingerprint`/`IpIntelligence` row
   backs it — see section 4).
4. **AffordabilityEngine** (`src/engines/affordability.py`) — blends a wallet-activity score (via
   `WalletAdapter`, currently `MockJazzCashAdapter` — **hardcoded `55.0` for every user, see
   section 4**) with `BankStatementAnalysis` (avg balance / salary detected / expense ratio / NSF
   events) when one exists, 50/50 weighted. No bank statement on file → `income_signal="unknown"`
   and the `bank_data_unavailable` flag.
5. **ScoringEngine** (`src/engines/scoring.py`) — a hand-set, additive WOE-style points scorecard
   (not ML — see section 4): identity score and alt-data score are each binned per
   `RulePolicy.identity_score_bins`/`alt_data_score_bins` and the matched bins' points summed into
   a 0-900 raw score, then banded:

   | Band | Score cutoff | Base limit (PKR) | Down payment | Cold-start cap (PKR) |
   |---|---|---|---|---|
   | A | ≥800 | 25,000 | 25% | 8,000 |
   | B | ≥700 | 15,000 | 25% | 5,000 |
   | C | ≥600 | 8,000 | 30% | 3,000 |
   | D | ≥500 | 5,000 | 35% | 2,000 |
   | F | <500 | 0 | — | — |

   A score below `settings.auto_decline_below` (**600** — note: `config.py`'s
   `auto_approve_threshold`/`manual_review_threshold` fields exist but are **dead config**, never
   read anywhere in the pipeline) is an automatic reject regardless of band math.
6. **LimitEngine** (`src/engines/limit.py`) — applies a category multiplier (e.g. smartphones
   ×0.60, gold jewelry ×0.40, laptops ×0.65; a multiplier below 0.7 also bumps the required down
   payment by 5 points, capped at 60%), then the cold-start cap (see section 4 — this fires far
   more often than the name implies), then a portfolio-concentration check (this user's existing
   approved exposure + this order must not exceed `settings.maximum_limit` = 500,000 PKR
   platform-wide cap), then clamps to that same maximum.

**Outcome logic** (`DecisionEngine`, `src/engines/decision.py`) — the financed amount is
`order_amount × (1 − down_payment_pct/100)` (credit only covers the post-down-payment portion):

- `financed_amount ≤ limit` → **`approved`**: `approved_limit`, `down_payment_pct` as computed.
- Otherwise, if raising the down payment (up to `policy.max_suggested_down_payment_pct` = 45%,
  deliberately stricter than the 60% overlay cap) would bring the financed amount within the
  limit → **`increase_down_payment`**: `approved=false`, but this is a counter-offer, not a
  decline — `suggested_down_payment_pct` tells the frontend what down payment would make the same
  order work. **UI guidance: do not show this as a rejection; show "increase your down payment to
  X% to proceed" and let the customer retry with that value.**
- Otherwise, if the limit still covers at least `partial_approval_min_coverage_ratio` (50%) of the
  order → **`partial_approval`**: `approved=true`, `approved_limit` < `requested_amount`. **UI
  guidance: this is a real approval at a reduced amount — show the reduced figure clearly, not a
  full-order confirmation.**
- Otherwise → **`rejected`**: `approved=false`, `risk_band="F"`, `approved_limit=0.0`,
  `rejection_reason` set.

`manual_review_required` can be `true` on *any* of the above outcomes (a borderline fraud score
doesn't block the decision, it just flags it for human follow-up afterward) — it is not a
separate outcome value.

Every decision carries an `explanation` dict (`ExplanationBuilder`,
`src/engines/explanation.py`): `summary` (human-readable one-liner), `top_factors` /
`factors: [{label, contribution, kind: positive|negative|neutral}]` (exact point contributions,
since the scorecard is additive — not an approximation), `flags: list[str]` (see
`packages/shared-python/sk_shared/credit_reason_codes.py::FlagCode` for the full enum of ~35
codes this pipeline can emit), `layer_scores: {identity_score, alt_data_score, ml_score}`,
`model_version` (currently `"scorecard-v1"`), and `policy_version` (stamped on by the pipeline so
a historical decision's explanation never silently changes if the policy is later edited). This
is what a support/admin UI would render to explain a decision to a customer or a dispute team.

## 4. Known Gaps & Caveats Relevant to Integration

Verified against the current code on this pass (2026-08-28), not carried forward from any prior
report's summary table:

- **Alt-data/wallet scoring is still a hardcoded mock — OPEN.** `src/adapters/wallet.py`'s
  `MockJazzCashAdapter.get_activity_score` returns a fixed `55.0` for every user, always. There is
  no real JazzCash/Easypaisa integration. **Do not build any UI copy implying "we analyze your
  wallet/mobile-money activity" — it is a fixed number, not a signal, for every single applicant.**
- **Device-fingerprint / IP-intelligence / synthetic-identity signals are dead code — OPEN.**
  Confirmed by repo-wide search: `DeviceFingerprint`, `IpIntelligence`, and
  `SyntheticIdentityIndicator` rows are constructed only in `apps/credit-engine/tests/`, never by
  any application code path. Every real applicant scores `0` on the device/IP trust component of
  `IdentityEngine` and contributes nothing to `FraudEngine`'s composite score — not because they're
  low-risk, but because no ingestion pipeline exists. A frontend passing
  `device_fingerprint_hash`/relying on the client IP is not wrong to do so (the plumbing is there
  and will light up automatically once a real vendor is wired in), but no such vendor exists today.
- **Cold-start cap is now only *partially* mitigated — was OPEN, now PARTIAL.** Because the two
  gaps above mean `device_trust_unverified` / `ip_trust_unverified` / `bank_data_unavailable` are
  always true for a real applicant, `apply_cold_start_cap` (`src/engines/limit.py`) would fire on
  *every* decision forever, silently capping e.g. a Band-A customer's real 25,000 limit to 8,000
  even on their 50th order. Current code adds a real escape valve:
  `LimitEngine.has_repayment_track_record` graduates a user out of the cap once they have at least
  `policy.graduation_min_repaid_loans` (3) fully-repaid loans with **zero** history anywhere of a
  late fee or an overdue/defaulted installment. This is a genuine fix for *proven repeat
  customers*, but **every first-time and early customer is still cold-start-capped, unconditionally,
  by design** (that's the intended behavior, not a residual bug) — do not build UI that implies
  limit growth is continuous or score-driven for a new user; it only unlocks after 3 clean loans.
- **No ML model exists anywhere in this service — OPEN, and not really a "bug."**
  `ScoringEngine` is an honestly-documented hand-set additive scorecard (`src/engines/scoring.py`
  says so in its own docstring). Zero ML dependencies in `pyproject.toml`. Any external product
  copy claiming "AI/ML-based underwriting" or "XGBoost/LightGBM" is not accurate for this service
  as it exists today.
- **Portfolio-concentration TOCTOU race — FIXED.** `POST /credit/apply` now holds a per-user Redis
  lock (`_portfolio_lock_key`, SETNX, 30s TTL) spanning the portfolio check through the
  `CreditApplication` commit, plus a `SELECT ... FOR UPDATE` on the user's row inside
  `LimitEngine.check_portfolio_concentration` as a second, DB-level layer (a no-op on SQLite, real
  on Postgres). A second concurrent `/credit/apply` for the same user now fails fast with `409`
  instead of racing. Confirmed present in `apps/credit-engine/src/api/routes.py` lines ~37-57,
  143-151 and `src/engines/limit.py` lines ~156-165.
- **`/credit/apply` synchronous-Gateway-callback latency — FIXED.** The Gateway sync
  (`push_credit_result`, up to 3 retries × 5s timeout ≈ worst case 16.5s) now runs via
  `BackgroundTasks.add_task` after the HTTP response is already sent, not awaited inline — confirmed
  in `src/services/pipeline.py::create_credit_application`. Note this fix is specific to the
  `/credit/apply` route, which supplies a real `BackgroundTasks`; the async worker
  (`src/workers/credit_assess_consumer.py`) has no request context and still awaits
  `push_credit_result` synchronously, which is fine there since nothing is waiting on an HTTP
  response.
- **`utilized_amount` in `GET /credit/status`/`/credit/me` is hardcoded to `0.0`.** Credit-engine
  does not itself track drawn-vs-repaid balance (that lives in payment-orchestrator/ledger-service's
  `Loan`/`Installment` tables). `available_limit` in this response is therefore always equal to
  `current_limit`, never reduced by outstanding balance. **A frontend must not treat this
  endpoint's `available_limit` as "how much can I still borrow right now"** — Gateway's own
  `GET /api/v1/credit/status` (a separate, Gateway-owned implementation) computes a real
  `available = limit − active_loan_outstanding` and is the correct source for that number.
- **No automated limit-increase job.** `config.py` defines `credit_increase_after_n_payments` (3)
  and `credit_increase_pct` (0.25) but nothing in the codebase reads either field — confirmed by
  grep. `POST /credit/recalculate` computes what a limit *would* be today but never applies it; the
  only way a customer's live limit actually changes is `/admin/credit/override` (human-triggered)
  or a fresh `/credit/apply` decision. Don't build UI copy implying automatic limit growth from
  timely payments — it doesn't exist as an automated feature yet, only the graduation-from-cold-start
  mechanism above.
- **No route-level RBAC inside credit-engine.** Any admin JWT (any `admin_id` that resolves to a
  live, non-deleted `admin_users` row) can call every `/admin/*` route here — there is no
  per-permission check equivalent to Gateway's `manage_risk`/`manage_admins` RBAC. If per-role
  restriction on override/blacklist actions matters, it needs to be enforced upstream (Gateway) or
  added here; today it is not enforced by this service at all.

## 5. Auth & Headers

**Credit-engine is never called directly by a browser or mobile app, in any environment.** This
is stated explicitly in `src/main.py`'s own comment ("No CORS here deliberately: credit-engine is
only ever called server-to-server... nothing in this fleet has a browser talk to it directly") and
is independently confirmed by infrastructure:

- `infra/k8s/base/network-policies/12-credit-engine.yaml` — the only allowed ingress to
  credit-engine's pods is from pods labeled `app: gateway`, on port 8000. Nothing else in the
  cluster (including web-customer/web-admin) can reach it.
- `infra/k8s/overlays/production/ingress.yaml` — the public ingress routes only to `gateway` (plus
  the two frontend apps being discarded); credit-engine has no public hostname/path at all.
- No CORS middleware is configured (`app.add_middleware` calls in `src/main.py` are logging +
  request-ID only).

**More importantly for a new integration: as of this reading, nothing in `apps/gateway/`'s source
calls credit-engine's HTTP API at all.** There is no `CREDIT_ENGINE_URL` config or HTTP client for
it anywhere in Gateway. The two integration paths that actually exist today are:

1. **Async, queue-driven (the only live trigger today):** Gateway's KYC-approval flow
   (`apps/gateway/src/services/kyc_queue.py`) pushes a `{"event": "kyc.approved", "user_id": ...}`
   job onto the Redis list `sk:queue:credit_assess` when an admin approves a user's KYC.
   Credit-engine's worker (`src/workers/credit_assess_consumer.py`, run as a separate process —
   not the FastAPI app) pops it, calls `CreditPipelineService` **directly in-process** (not over
   HTTP), and pushes the resulting decision back to Gateway via the callback below. This is what
   actually sets a brand-new customer's initial credit limit after KYC approval.
2. **Outbound HTTP callback, credit-engine → Gateway:** `src/core/http_client.py::push_credit_result`
   POSTs to Gateway's `/internal/users/{user_id}/credit-result` with header
   `X-Internal-Token: <INTERNAL_SERVICE_TOKEN shared secret>` (same convention every other internal
   service in this fleet uses to call Gateway) plus `X-Request-ID` for trace correlation. Retries
   up to 3× with exponential backoff on 5xx/network errors; does not retry 4xx. Called from
   `/credit/apply` (backgrounded), `/admin/credit/override`/`/adjust` (awaited inline), and the
   worker (awaited inline, no request context to background it against).
3. **The full `/credit/*` and `/admin/credit/*` HTTP API documented in section 2 is built,
   network-reachable from Gateway, and JWT-auth-gated exactly as if it were meant to be called
   live per-request** — but nothing currently issues those calls. Gateway's own
   `GET /api/v1/credit/status` and `GET /api/v1/credit/history` (`apps/gateway/src/api/v1/credit.py`)
   independently re-read Gateway's own `users`/`RiskAssessment`/`CreditLimitHistory` tables rather
   than proxying to credit-engine, and Gateway's order-time credit check
   (`apps/gateway/src/services/order_service.py`) compares the order total against the cached
   `user.available_credit` field rather than calling `/credit/check` live. **A new frontend team
   integrating against this backend should assume all customer/admin traffic goes through Gateway,
   never to credit-engine directly** — and if a live per-order credit check
   (`/credit/check`/`/credit/prequalify`) or a live application flow (`/credit/apply`) is wanted
   from a new frontend, Gateway needs a new route added to proxy to it; today no such route exists.

**JWT shape required by this service:** RS256, verified against `settings.JWT_PUBLIC_KEY` (the
same key Gateway signs with). Customer routes require the `user_id` claim; admin routes require
`admin_id`. There is no separate "internal service token" mode for *incoming* requests to this
service's `/credit/*`/`/admin/*` routes — every inbound request must carry a real user or admin
JWT, even though network policy already restricts who can reach it. The
`X-Internal-Token`/`INTERNAL_SERVICE_TOKEN` mechanism described above is only for this service's
*outbound* calls to Gateway, not for authenticating callers of this service.
