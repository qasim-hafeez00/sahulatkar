# Payment Gateway Integration Specification

**Status:** STABLE (what's documented) — per-provider technical integration detail (request/response schemas, specific API endpoints) is not present in the reviewed engineering docs beyond the summary level below; recommend a dedicated integration guide per provider be authored by whoever holds the actual API credentials/contracts.

## Safepay

- **Coverage:** universal (cards + wallets).
- **Fee:** 2.9% + PKR 30 per transaction.
- **Settlement:** T+2.
- **Flow:** asynchronous redirect — customer leaves the app, completes payment on Safepay's hosted page, returns via a redirect URL.
- **Webhook:** `POST /webhooks/safepay`, HMAC-SHA256 verified; on `payment:created` + `state: PAID`, marks the installment paid.
- **Known gap:** the post-payment redirect URL is not currently configured (`GW-BL-06`-adjacent finding in the audit's Step 8 walkthrough).

## JazzCash

- **Coverage:** 40M+ wallet users.
- **Fee:** 1.5–2%.
- **Settlement:** T+1, via SFTP settlement file (currently mocked, see [`../02-business-workflows/11-merchant-settlement-reconciliation.md`](../02-business-workflows/11-merchant-settlement-reconciliation.md)).
- **Flow:** synchronous direct API.
- **Webhook:** `POST /webhooks/jazzcash`, HMAC verified; on `pp_ResponseCode: "000"`, same handling as Safepay's success path.

## EasyPaisa

- **Coverage:** 35M+ wallet users.
- **Fee:** 1.5–2%.
- **Settlement:** T+1.
- **Flow:** synchronous direct API, mirrors JazzCash's pattern.
- **Adapter status:** listed in the architecture but the audit notes its implementation status is not independently verified/validated in the routing engine (`PO-CRIT-06`).

## Raast

- **Coverage:** SBP's instant payment rail.
- **Fee:** ~0%.
- **Settlement:** T+0.
- **Status:** Phase 4 target, not yet live. Mandate lookup for recurring auto-debit is referenced in code but not implemented (`PO-CRIT-03`).

## Stripe Issuing (VCN issuer, MVP)

- **Role:** issues the single-use virtual cards the checkout agent spends against merchants — not a customer-collection gateway.
- **Known gaps:** no webhook receiver for Stripe events like `issuing_card.updated` (`PO-CRIT-05`); expired-card voiding on the issuer side is not wired (`PO-CRIT-04`).
- **Planned migration:** Lithic, at scale (per the platform's stated stack).

## Common integration standards across all gateways

HMAC-SHA256 webhook signature verification (see [`../06-api-events/23-api-standards.md`](../06-api-events/23-api-standards.md)); webhook deduplication by provider transaction ID is the platform standard but **not consistently implemented today** (`GW-BL-13`).

## Related documents

[`99-payment-architecture.md`](99-payment-architecture.md), [`../06-api-events/23-api-standards.md`](../06-api-events/23-api-standards.md), [`../02-business-workflows/08-payment-workflow.md`](../02-business-workflows/08-payment-workflow.md).
