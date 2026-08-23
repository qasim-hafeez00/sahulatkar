# External Integration Documentation (Index)

**Status:** STABLE (index) — per-provider deep integration guides (request/response schemas, credential setup, rate limits) do not exist as standalone documents in this knowledge base pass; this index instead points to where each provider's integration is currently documented and flags its implementation status, so a reader knows where to look and what to expect.

| Provider | Role | Documented in | Implementation status |
|---|---|---|---|
| NADRA Verisys | CNIC identity verification | [`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md) | **Stub — no real API call made** |
| Shufti Pro (or uqudo/Jumio) | OCR, liveness, face match | [`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md) | **Stub** |
| TASDEEQ | Credit bureau reporting | [`../11-compliance/36-compliance-requirements-matrix.md`](../11-compliance/36-compliance-requirements-matrix.md) | Referenced, not confirmed live |
| Stripe Issuing | VCN issuance | [`../19-payments-financial-operations/101-payment-gateway-integration-specification.md`](../19-payments-financial-operations/101-payment-gateway-integration-specification.md) | Implemented, with known gaps (webhook receiver, void-on-expiry) |
| Safepay | Payment collection | [`../19-payments-financial-operations/101-payment-gateway-integration-specification.md`](../19-payments-financial-operations/101-payment-gateway-integration-specification.md) | Implemented, redirect URL not configured |
| JazzCash | Payment collection, SMS | [`../19-payments-financial-operations/101-payment-gateway-integration-specification.md`](../19-payments-financial-operations/101-payment-gateway-integration-specification.md) | Implemented |
| EasyPaisa | Payment collection | [`../19-payments-financial-operations/101-payment-gateway-integration-specification.md`](../19-payments-financial-operations/101-payment-gateway-integration-specification.md) | Status not independently verified |
| Raast | Instant payment rail | [`../19-payments-financial-operations/101-payment-gateway-integration-specification.md`](../19-payments-financial-operations/101-payment-gateway-integration-specification.md) | Phase 4, not live |
| AfterShip | Delivery tracking | [`../05-architecture/microservices/notification-service.md`](../05-architecture/microservices/notification-service.md) | Implemented |
| Rye API | Product extraction (Tier 1) | [`../05-architecture/microservices/product-service.md`](../05-architecture/microservices/product-service.md) | Implemented |
| BrightData | Residential proxies | [`../05-architecture/microservices/product-service.md`](../05-architecture/microservices/product-service.md) | Implemented |
| OpenAI (GPT-4o Vision) / Groq | Extraction fallback, self-healing | [`../05-architecture/microservices/product-service.md`](../05-architecture/microservices/product-service.md) | Implemented |
| 2Captcha / CapSolver | CAPTCHA solving | [`../05-architecture/microservices/product-service.md`](../05-architecture/microservices/product-service.md) | Implemented |
| Jazz SMS API | OTP/notification delivery | [`../05-architecture/microservices/notification-service.md`](../05-architecture/microservices/notification-service.md) | Implemented |
| Firebase (FCM) | Push notifications | [`../05-architecture/microservices/notification-service.md`](../05-architecture/microservices/notification-service.md) | Credential validation at startup not verified |
| SendGrid | Email delivery | [`../05-architecture/microservices/notification-service.md`](../05-architecture/microservices/notification-service.md) | Implemented; webhook unverified (security gap) |

## Recommended follow-up

For any provider marked "Stub" above and material to launch (NADRA and Shufti Pro specifically — they gate the entire KYC pipeline), a dedicated integration guide with actual API contracts should be authored once the integration is built, not left folded into the workflow documents as it is today.

## Related documents

[`23-api-standards.md`](23-api-standards.md), [`123-webhook-standards.md`](123-webhook-standards.md).
