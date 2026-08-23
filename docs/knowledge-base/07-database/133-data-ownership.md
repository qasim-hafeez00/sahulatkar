# Data Ownership

**Status:** STABLE — restates [`../05-architecture/21-service-responsibility-matrix.md`](../05-architecture/21-service-responsibility-matrix.md)'s service-to-table mapping from the data-governance angle specifically (who may write to what), since that's a distinct concern from general service responsibility.

## Ownership principle

All 6 backend services share a single PostgreSQL instance (see [`25-database-architecture.md`](25-database-architecture.md), ADR-004 in [`../14-project-management/44-architecture-decision-records.md`](../14-project-management/44-architecture-decision-records.md)) — table ownership is enforced by **convention and code review**, not physical database separation or database-level access grants per service.

## Ownership by domain

| Domain | Owning service | Tables (examples) |
|---|---|---|
| Identity/Auth | Gateway | `users`, `admin_users`, `user_sessions` |
| KYC | Gateway | `user_kyc_verifications`, `user_devices`, `kyc_verification_queue` |
| Contracts | Gateway | `wakalah_agreements`, `murabaha_contracts`, `contract_digital_signatures` |
| Catalog/Extraction | Product Service | `products`, `scraping_jobs`, `merchants`, `prohibited_categories` |
| Credit/Risk | Credit Engine | `credit_applications`, `risk_assessments`, `blacklisted_entities`, `fraud_rules` |
| Payments | Payment Orchestrator | `loans`, `installments`, `payment_transactions`, `virtual_cards` |
| Ledger | Ledger Service | `ledger_accounts`, `journal_entries`, `journal_entry_lines`, `late_fee_charity_allocations` |
| Delivery/Notifications | Notification Service | `shipments`, `tracking_events`, `couriers`, notification/template tables |

## Real risk of convention-only enforcement

Because there's no database-level guard against, say, Notification Service writing directly to `loans`, ownership violations would only be caught by code review discipline — and the audit's cross-service duplication findings (e.g., audit-trail recording implemented independently in both Gateway and Notification Service, per [`../05-architecture/21-service-responsibility-matrix.md`](../05-architecture/21-service-responsibility-matrix.md)) suggest this discipline isn't perfectly maintained. Recommend, at minimum, per-service database roles/grants (the `sk_app`, `sk_admin_api` roles referenced in `docs/DATABASE_GUIDE.md` are a start, but appear to be broad application-wide roles rather than per-service, table-scoped grants) if stricter enforcement is desired.

## Related documents

[`../05-architecture/21-service-responsibility-matrix.md`](../05-architecture/21-service-responsibility-matrix.md), [`25-database-architecture.md`](25-database-architecture.md).
