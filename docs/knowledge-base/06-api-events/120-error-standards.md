# Error Standards

**Status:** STABLE — expanded from [`23-api-standards.md`](23-api-standards.md) with the full observed error-code vocabulary in one place.

## Shape

```json
{ "detail": "MACHINE_READABLE_CODE" }
```

FastAPI's standard `HTTPException` response shape, with the platform convention being a SCREAMING_SNAKE_CASE machine-readable string in `detail` rather than a free-text message — this is a good, consistent, testable pattern that should be maintained for all new endpoints.

## Full observed error-code vocabulary (as of this documentation pass)

| Code | HTTP status | Meaning |
|---|---|---|
| `PHONE_ALREADY_REGISTERED` | 409 | Registration attempted for an existing phone |
| `INVALID_PHONE_FORMAT` | 422 | Non-E.164 phone |
| `INVALID_OTP` | 400 | Wrong OTP code |
| `OTP_EXPIRED` | 400 | OTP past its 3-minute TTL |
| `TOO_MANY_ATTEMPTS` | 429 | OTP attempt limit exceeded |
| `CNIC_BLOCKED` | 422 | NADRA reports CNIC blocked |
| `CNIC_EXPIRED` | 422 | CNIC expiry passed |
| `OCR_FAILED` | 422 | CNIC OCR extraction failed |
| `NADRA_UNAVAILABLE` | 503 | NADRA API unreachable — queued for retry |
| `LIVENESS_FAILED` | 422 | Liveness check failed |
| `FACE_MISMATCH` | 422 | Face-match score too low |
| `NOT_A_PRODUCT_URL` | 422 | Extraction determined the URL isn't a product page |
| `PROHIBITED_CATEGORY` | 422 | Shariah-blocked product category |
| `OUT_OF_STOCK` | 422 | Product unavailable |
| `DOES_NOT_SHIP_TO_PAKISTAN` | 422 | Shipping restriction |
| `MURABAHA_NOT_SIGNED` | 403 | Hard gate — VCN issuance blocked |
| `CONFIRMATION_REQUIRED` | 400 | Murabaha signing missing the confirmation checkbox |
| `ALREADY_SIGNED` | 409 | Duplicate signing attempt |

## Gaps

Some endpoints return generic 500s where a specific code/status would be correct (e.g., Ledger Service's `GET /api/entries/{entry_number}` returning 500 instead of 404 on a missing entry, `LS-EP-04`) — every such instance found should be treated as a bug against this standard, not an acceptable exception.

## Recommended addition

A machine-readable error-code registry (even a simple shared enum in `sk_shared`) would prevent two services from independently inventing a differently-spelled code for the same underlying condition — not currently maintained as a single source of truth.

## Related documents

[`23-api-standards.md`](23-api-standards.md).
