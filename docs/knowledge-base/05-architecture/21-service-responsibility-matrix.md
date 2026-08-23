# Service Responsibility Matrix

**Status:** STABLE

| Service | Port | Redis DB | Owns | Does NOT own |
|---|---|---|---|---|
| **Gateway** | 8000 | 0 | Auth, JWT issuance, RBAC, rate limiting, hard-gate enforcement, request routing, KYC orchestration, contract generation/signing | Actual product extraction, credit scoring logic, payment processing, ledger truth |
| **Product Service** | 8001 | 1 | URL normalization, extraction waterfall, Universal Product Object (UPO), prohibited-category checks, pricing/Murabaha calculation, checkout automation (Playwright agent) | Auth, credit decisions, payment execution, financial records |
| **Credit Engine** | 8002 | 2 | 7-layer credit/fraud scoring, risk bands, credit limits, blacklist management | Payments, contracts, order orchestration |
| **Payment Orchestrator** | 8003 | 3 | VCN lifecycle (issue/void/status), down payment + installment collection, gateway adapters (Safepay/JazzCash/EasyPaisa), gateway-settlement reconciliation | Ledger truth (posts to Ledger Service, doesn't own the books), UI |
| **Ledger Service** | 8004 | 4 | Double-entry bookkeeping, chart of accounts, billing sweep (identifying due installments), charity routing, financial statements (P&L, balance sheet) | Payment execution (only records the result), UI |
| **Notification Service** | 8005 | 5 | SMS/WhatsApp/push/email dispatch, delivery tracking (AfterShip integration), notification preferences/templates | Financing decisions, payment processing |

## Ownership boundaries worth calling out explicitly

- **Ledger owns financial truth, Payment Orchestrator owns execution.** A payment being `CAPTURED` in Payment Orchestrator and a journal entry existing in Ledger Service are two different facts that must be kept in sync via events — the known gap here (uncompensated cross-service transactions, see [`../02-business-workflows/07-bnpl-workflow-e2e.md`](../02-business-workflows/07-bnpl-workflow-e2e.md)) is exactly a boundary-consistency failure, not a design flaw in the boundary itself.
- **Gateway owns contract signing, but not what happens after.** Gateway creates the `Loan` record on Murabaha signing; Ledger Service is supposed to react to that via an event (`loan.created`) it currently never receives — see the same cross-service gap.
- **Product Service owns the checkout agent, not the money.** The agent spends via a VCN it doesn't issue (Payment Orchestrator issues it) and doesn't control (Payment Orchestrator can void it) — a deliberate separation so a compromised/misbehaving checkout automation can't unilaterally move money beyond what a VCN's spend controls (MCC lock, amount cap) already prevent.
- **No service owns "merchants" in a CRM sense**, because there is no merchant relationship to manage — see [`../02-business-workflows/06-merchant-vendor-journey.md`](../02-business-workflows/06-merchant-vendor-journey.md). Product Service tracks merchant *metadata* (domain, scrape config, checkout success rate) purely for its own extraction/checkout reliability, not as a partner record.

## Duplicated logic across service boundaries (from the 2026-04-27 code audit)

Flagging these here because they represent a boundary that isn't as clean in code as this matrix implies it should be:

| Duplicated logic | Where | Should live in |
|---|---|---|
| Audit trail recording | Gateway `core/audit.py` and ad-hoc inserts in Notification Service admin code | `sk_shared` (Gateway is the correct conceptual owner) |
| HMAC verification | Gateway webhook handler and Notification Service `core/utils.py`, implemented independently | `sk_shared/security.py` |
| Cursor-based pagination | Reimplemented separately in Gateway and Product Service | `sk_shared/pagination.py` (which already exists and should be the single implementation) |
| Rate-limiting decorator | Reimplemented separately in Gateway and Payment Orchestrator | Not yet shared via `sk_shared` |
| HITL queue | Two separate systems: Gateway's KYC HITL queue and Product Service's extraction-failure HITL queue, potentially writing to the same underlying table | Should be one unified HITL queue owned by a single service |

## Related documents

[`20-system-architecture.md`](20-system-architecture.md), [`22-microservice-documentation.md`](22-microservice-documentation.md), [`../06-api-events/24-event-catalog.md`](../06-api-events/24-event-catalog.md).
