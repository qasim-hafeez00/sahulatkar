# Notification Service

**Status:** STABLE (design) — ~80% complete per audit.

## Purpose

All customer-facing communication (SMS, WhatsApp, push, email, in both Urdu and English) plus delivery tracking via AfterShip.

## Responsibilities

- Multi-channel dispatch: SMS (Jazz), push (Firebase/FCM), email (SendGrid), WhatsApp.
- OTP delivery (registration, login, contract signing).
- Delivery tracking: AfterShip webhook ingestion across TCS/Leopards/PostEx/M&P couriers, status mapping, `delivered` → intended to trigger installment activation.
- Notification templates, scheduling, DLQ management, per-user preferences.

## Dependencies

Jazz SMS API, Firebase Cloud Messaging, SendGrid, AfterShip, Redis (event listening, DLQ), PostgreSQL.

## Key APIs

`POST /webhooks/aftership` (HMAC-verified), `POST /tracking/register`, `GET /tracking/{order_id}`, notification list/preferences/unsubscribe, admin template/DLQ management. Full spec: `docs/System-md-files/M10-M12-delivery-ledger-admin.md` (M10 section).

## Events

Consumes a defined `EVENT_CATEGORY_MAP` of expected events. **Several are never actually published by any source service** — see the table below.

## Database ownership

`shipments`, `tracking_events` (TimescaleDB hypertable, 7-day compression, 2-year retention), `couriers`, notification/template/preference tables.

## Missing events (expected but never published — from `docs/PRODUCTION_GAPS_REPORT.md` §6.4)

| Expected event | Should be published by | Real-world impact |
|---|---|---|
| `billing.installment_overdue` | Ledger `BillingSweepWorker` | Customers get pre-due reminders but no notice once actually overdue |
| `order.cancelled` (to notifications) | Gateway | No notification on order cancellation |
| `vcn.expired` | Payment Orchestrator | No notification when a VCN expires |
| `payment.failed` (auto-debit) | Payment Orchestrator | No notification on failed auto-collection |
| `kyc.documents_needed` | Gateway | No prompt to resubmit KYC documents |
| `credit.limit_changed` | Gateway | No notification when credit limit changes |

## Known gaps (from `docs/PRODUCTION_GAPS_REPORT.md` §6)

- **NS-BUG-01 (high):** registration OTPs for not-yet-registered users are attributed to `user_id=1` (super admin), polluting the admin audit trail.
- **NS-BL-01 (high):** the SendGrid webhook has no signature verification — anyone can POST to it and trigger unsubscribe/preference changes.
- **NS-BL-09 (medium):** `ScheduledNotification` records exist but no worker actually fires them — scheduled messages never send.
- Full checklist: `docs/PRODUCTION_GAPS_REPORT.md` §6, §13.
