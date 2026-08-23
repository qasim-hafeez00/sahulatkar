# Webhook Standards

**Status:** STABLE — expanded from [`23-api-standards.md`](23-api-standards.md).

## The standard

Every inbound webhook must: (1) verify an HMAC-SHA256 signature against a provider-specific shared secret before processing, and (2) deduplicate by the provider's own transaction/event ID before acting, so a redelivered webhook (common — most providers retry on a non-2xx or timeout) never causes a duplicate side effect.

## Compliance against this standard, per current webhook

| Webhook | HMAC verified? | Deduplicated? |
|---|---|---|
| AfterShip (`X-Aftership-Hmac-Sha256`) | Yes | Not confirmed |
| JazzCash | Yes | **No** (`GW-BL-13`) |
| Safepay | Yes | **No** (`GW-BL-13`) |
| SMS delivery | HMAC optional | Not confirmed |
| WhatsApp delivery | HMAC optional | Not confirmed |
| SendGrid | **No signature verification at all** (`NS-BL-01`) | Not confirmed |

## The SendGrid gap deserves its own callout

Every other webhook at least attempts HMAC verification (even if some make it optional rather than mandatory). SendGrid's webhook has **none** — meaning anyone who discovers the endpoint URL can currently POST arbitrary payloads to it and trigger unsubscribe/preference changes for any user. This should be treated as a standards violation to fix immediately, not just a documentation gap.

## Recommended response codes

A webhook receiver should return 200 quickly (acknowledge receipt) and process asynchronously where possible, to avoid the provider's own retry logic firing due to slow processing rather than actual failure — not explicitly confirmed as the current pattern across all six webhooks above.

## Related documents

[`23-api-standards.md`](23-api-standards.md), [`../08-security/27-security-architecture.md`](../08-security/27-security-architecture.md).
