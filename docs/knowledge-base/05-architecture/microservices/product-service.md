# Product Service

**Status:** STABLE (design) — ~60% complete per audit, blocked by checkout-agent completeness.

## Purpose

Turns any product URL into a structured, priced financing offer, and executes the actual purchase via an autonomous browser agent once a VCN is issued.

## Responsibilities

- URL normalization (shortlink expansion, tracking-param stripping, platform detection).
- Extraction waterfall: Rye API → JSON-LD → Playwright+LLM → HITL, producing a Universal Product Object (UPO).
- Prohibited-category checking (Shariah Rule 3) before any offer is generated.
- Murabaha pricing calculation (cost + markup by plan).
- Checkout automation: Playwright + stealth + BrightData proxies + VLM self-healing, executing the actual purchase using an issued VCN.
- Merchant metadata tracking (`merchants` table) for extraction/checkout reliability tuning — not a partner relationship, see [`../../02-business-workflows/06-merchant-vendor-journey.md`](../../02-business-workflows/06-merchant-vendor-journey.md).

## Dependencies

Rye API, BrightData (residential proxies), Groq/OpenAI (LLM extraction + VLM self-healing), 2Captcha/CapSolver (CAPTCHA solving), Redis (job queues), PostgreSQL, Payment Orchestrator (VCN decrypt endpoint, internal).

## Key APIs

`POST /products/extract`, `GET /products/jobs/{job_id}`, `GET /products/{upo_id}/offer`, `GET /products/search`, `POST /agent/queue-job`, `GET /agent/job/{job_id}/status` (SSE). Full spec: `docs/System-md-files/M03-url-pipeline.md`, `M06-M09-payments-vcn-agent-hitl.md` (M08 section).

## Events

Publishes `product.extracted`; consumes `vcn.issued` (triggers checkout queue) and `order.cancelled` (should cancel in-flight checkout — race condition noted below).

## Database ownership

`products`, `scraping_jobs`, `prohibited_categories`, `merchants`, `purchase_executions`.

## Known gaps (from `docs/PRODUCTION_GAPS_REPORT.md` §3)

- **PS-BUG-01/02 (critical):** the scraping worker crashes on every job (undefined variable, `scraping_worker.py:117`); the prohibited-category check is not actually called before a product is saved (`scraping_worker.py:207`) — both are launch blockers.
- **PS-BL-02 (critical, compliance):** the tiered Murabaha markup has an open `TODO` for Shariah board sign-off — see [`../../04-shariah/19-shariah-review-register.md`](../../04-shariah/19-shariah-review-register.md).
- **PS-BL-03 (critical):** `CheckoutFormFiller.run_checkout()` — the code that actually fills in VCN payment details and detects order confirmation — is an incomplete stub. **No automated purchase can complete end-to-end today.** This is the single most consequential functional gap in the platform, since it blocks the entire value proposition.
- **PS-BL-01 (high):** URL-based prohibited-category checking (`check_url()`) is incomplete — parses domain only, no blacklist lookup.
- Full checklist: `docs/PRODUCTION_GAPS_REPORT.md` §3, §13.

## Security note

`GET /api/v1/internal/vcn/{order_id}/decrypt` (called by this service to retrieve plaintext VCN details for checkout) currently has **no rate limiting** — a compromised Product Service instance or leaked internal token could mass-exfiltrate VCN credentials (`PO-BL-01`). See [`../../08-security/27-security-architecture.md`](../../08-security/27-security-architecture.md).
