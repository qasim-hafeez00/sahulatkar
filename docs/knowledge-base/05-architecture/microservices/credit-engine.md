# Credit Engine

**Status:** STABLE (design) — noted as "Done" in `docs/MASTER_PLAN.md`'s completed-components table; excluded from the scope of `docs/PRODUCTION_GAPS_REPORT.md` (that audit explicitly covers "all microservices EXCEPT credit-engine"), so this service's functional-completeness has not been independently re-verified for this knowledge base pass.

## Purpose

Real-time (<3s SLA) credit and fraud decisioning for every order, using a 7-layer pipeline tuned for thin-file Pakistani users.

## Responsibilities

- Layer 1–7 scoring pipeline (hard blocks, velocity, identity/device, alternative data, ML scoring, category overlay, portfolio controls) — full detail in [`../../03-bnpl-financing/14-eligibility-rules.md`](../../03-bnpl-financing/14-eligibility-rules.md).
- Credit band assignment and limit/down-payment determination — [`../../03-bnpl-financing/15-credit-limit-rules.md`](../../03-bnpl-financing/15-credit-limit-rules.md).
- Blacklist management (CNIC/phone/device/IP/merchant).
- Fraud rule configuration (`fraud_rules` table — condition-driven, editable without a code deploy by design).
- SHAP-based decision explainability for declined/borderline applications.

## Dependencies

Redis (sub-millisecond hard-block and velocity checks), PostgreSQL (application/assessment history), JazzCash API (alternative data), KYC signals from Gateway.

## Key APIs

`GET /credit/check` (internal, called by Gateway, <3s p99 SLA), `GET /credit/me` (customer), `POST /admin/credit/adjust`, `GET /admin/risk/alerts`, `POST /admin/risk/blacklist`, `GET /credit/explain/{credit_app_id}`. Full spec: `docs/System-md-files/M04-credit-engine.md`.

## Database ownership

`credit_applications`, `risk_assessments`, `credit_limit_history`, `blacklisted_entities`, `fraud_rules`, `velocity_checks`.

## Known gaps

Not covered by the 2026-04-27 code audit (out of scope by that report's own stated boundary). No independently verified gap list exists for this service in current documentation — **recommend a dedicated credit-engine code audit**, matching the rigor applied to the other five services, before treating this service's production-readiness as confirmed. Two cross-cutting items are known from the other services' audits and do affect this service's real-world behavior even if the service's own code wasn't reviewed: (1) `GET /credit/status` in Gateway may serve a stale `credit_limit` because it doesn't force a refresh after this service updates it (`GW-BL-07`); (2) `system_parameters`-driven policy values (auto-approve threshold, max limit, etc.) are not actually configurable via the admin API yet (`GW-GAP-01`), so this service's policy parameters are effectively hardcoded regardless of the table above stating them as "configurable."
