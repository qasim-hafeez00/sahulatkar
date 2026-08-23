# Database Dictionary (Core Tables)

**Status:** STABLE for the tables listed — this is a curated core subset (the tables referenced across the module specs), not the full 169-table dictionary. Extending this to every table is flagged as follow-up work in the [README](../README.md) scope note.

Full column-level detail for every table below lives in the per-module source specs (`docs/System-md-files/M01`–`M12`) and `docs/Sahulatkar-docs/SahulatKar_DB_Design_Volume1/2.txt`; this dictionary indexes and summarizes rather than duplicating every column.

## Identity & Auth (Gateway)

| Table | Purpose | Key columns |
|---|---|---|
| `users` | Core customer identity | `phone` (E.164, unique), `password_hash` (bcrypt cost=12), `status` (`pending_kyc`/`active`/`suspended`/`closed`/`blocked`), `failed_login_attempts`, `locked_until` |
| `admin_users` | Internal staff accounts | `email`, `mfa_secret_encrypted` (AES-256), `mfa_enabled`, `force_password_change` |
| `user_sessions` | Active JWT sessions | `access_token_hash`/`refresh_token_hash` (SHA-256), `device_id`, `ip`, `expires_at`, `revoked_at` |
| `user_kyc_verifications` | KYC pipeline state | `nadra_request_id`, `nadra_raw_response` (JSONB, retained 7 years per SECP), `liveness_score`, `status`, `rejection_reason` |
| `user_devices` | Device fingerprinting | `device_fingerprint`, `is_rooted`, `is_emulator`, `risk_score`, `is_trusted` |
| `kyc_verification_queue` | Manual KYC review queue | `priority`, `assigned_to`, `sla_deadline` |

## Product & Extraction (Product Service)

| Table | Purpose | Key columns |
|---|---|---|
| `products` | Extracted product catalog | `canonical_url`, `current_price`, `is_prohibited`, `search_vector` (GIN full-text) |
| `scraping_jobs` | Extraction attempts (partitioned monthly) | `status`, `attempt_number`, `result` (JSONB raw UPO), `error_code` |
| `prohibited_categories` | Shariah-blocked categories | `keywords[]`, `shariah_basis` |
| `merchants` | Tracked third-party sites (not partners — see [`../02-business-workflows/06-merchant-vendor-journey.md`](../02-business-workflows/06-merchant-vendor-journey.md)) | `domain`, `checkout_success_rate`, `bot_detection_level`, `is_affiliate_partner`, `commission_rate` |

## Credit & Risk (Credit Engine)

| Table | Purpose | Key columns |
|---|---|---|
| `credit_applications` | One per credit decision request | `application_type`, `credit_score`, `bureau_score`, `status`, `approved_limit` |
| `risk_assessments` | Detailed per-order/onboarding score breakdown | `risk_band`, `flags[]`, `explanation` (JSONB), `model_version`, `processing_time_ms` |
| `credit_limit_history` | Immutable limit change log | `old_limit`, `new_limit`, `reason_code`, `changed_by_type` |
| `blacklisted_entities` | Fraud/risk blocklist | `entity_type`, `entity_value`, `severity`, `expires_at` |
| `fraud_rules` | Configurable fraud logic | `condition_json` (JSONB), `threshold`, `action` |
| `velocity_checks` | Sliding-window counters | `check_type`, `window_start`/`window_end`, `count`, `breached` |

## Contracts (Gateway)

| Table | Purpose | Key columns |
|---|---|---|
| `wakalah_agreements` | Agency authorization contract | `authorized_amount`, `price_variance_pct` (default 5%), `contract_hash` (SHA-256), `is_executed` |
| `murabaha_contracts` | Cost-plus sale contract | `cost_price`, `profit_amount`, `profit_rate_pct` (all `NOT NULL` — Shariah Rule 2), `total_repayable`, `installment_schedule` (JSONB), `validated_by_shariah_board` |
| `contract_digital_signatures` | OTP-signing audit record | `otp_hash` (SHA-256), `signed_at`, `ip`, `user_agent` |

## Payments & Financing (Payment Orchestrator)

| Table | Purpose | Key columns |
|---|---|---|
| `loans` | 1:1 with a signed order | `principal_amount`, `profit_amount`, `total_repayable`, `plan_type`, `status`, `total_outstanding` |
| `installments` | Individual scheduled payments | `due_date`, `status`, `late_fee_amount`, `retry_count`, critical partial index `(due_date, user_id) WHERE status='pending'` |
| `payment_transactions` | Gateway charge attempts (partitioned quarterly) | `gateway`, `gateway_txn_id` (unique), `status`, `retry_of_txn_id` |
| `virtual_cards` | VCN records | `masked_number`, `mcc_lock`, `authorized_amount`, `status`, PAN/CVV AES-256 encrypted (not shown as plain columns) |

## Ledger (Ledger Service)

| Table | Purpose | Key columns |
|---|---|---|
| `ledger_accounts` | Chart of accounts | `account_code`, `account_type`, `normal_balance` |
| `journal_entries` | Double-entry transaction header | `entry_type`, `source_type`/`source_id` (polymorphic), `is_balanced` |
| `journal_entry_lines` | Debit/credit line items | `debit_amount`, `credit_amount` (constraint: not both > 0 on one line) |
| `late_fee_charity_allocations` | Charity routing record | `late_fee_amount`, `charity_org_id`, `disbursed_at`, `receipt_s3` — immutable once disbursed |

## Delivery & Checkout (Product Service / Notification Service)

| Table | Purpose | Key columns |
|---|---|---|
| `purchase_executions` | Checkout agent attempt log | `status`, `failure_type`, `screenshot_s3`, `merchant_order_id` |
| `hitl_queue` | Human-in-the-loop escalations | `priority`, `assigned_to`, `sla_deadline` |
| `shipments` | 1:1 with an order | `courier_id`, `tracking_number`, `status` |
| `tracking_events` | TimescaleDB hypertable | `event_time`, `event_code`, `courier_raw_data` (JSONB) |
| `couriers` | Courier registry | `code`, `coverage_provinces[]`, `is_cod_available` |

## Data classification note

CNIC, IBAN, VCN PAN/CVV, and MFA secrets are the platform's designated encrypted-at-rest fields (`pgcrypto` AES-256). NADRA raw responses are retained 7 years per a cited SECP requirement — see [`../11-compliance/36-compliance-requirements-matrix.md`](../11-compliance/36-compliance-requirements-matrix.md) for the compliance basis (flagged there as unconfirmed pending legal review).

## Related documents

[`25-database-architecture.md`](25-database-architecture.md), `docs/Sahulatkar-docs/SahulatKar_DB_Design_Volume1.txt` and `Volume2.txt` (full original DB design research, kept in place as source material).
