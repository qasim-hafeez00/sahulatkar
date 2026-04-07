# M10 — Delivery & Tracking Service
  
**Phase**: 3 | **Sprint**: S13  
**Screen**: US-17 (Order Tracking)

---

## Purpose
Unified delivery tracking via AfterShip across TCS, Leopards, PostEx, M&P. Real-time status updates trigger user notifications. Delivery confirmation activates final installment.

---

## Database

```sql
shipments
  order_id BIGINT NOT NULL (1:1)
  courier_id BIGINT REFERENCES couriers(id)
  courier_name VARCHAR(100)           -- denormalized for display
  tracking_number VARCHAR(100) UNIQUE
  aftership_tracking_id VARCHAR(100)
  status CHECK ('label_created','picked_up','in_transit','out_for_delivery',
                'delivered','attempted','returned','lost')
  estimated_delivery DATE, actual_delivery TIMESTAMP

tracking_events (TimescaleDB hypertable on event_time)
  shipment_id, event_code VARCHAR(50)
  event_description TEXT, location_city
  courier_raw_data JSONB, event_time TIMESTAMP
  -- Compression after 7 days, retention 2 years

couriers
  name, code UNIQUE  -- 'TCS','LEO','MNP','POSTEX','SWYFT'
  tracking_url_template VARCHAR(512)
  api_endpoint, api_key_encrypted BYTEA
  coverage_provinces TEXT[]
  is_active BOOLEAN, is_cod_available BOOLEAN
  avg_delivery_days SMALLINT
  aftership_slug VARCHAR(50)
```

---

## APIs

### POST /webhooks/aftership
**Auth**: HMAC-SHA256 `X-Aftership-Hmac-Sha256` header  
**Logic**: Map AfterShip status to internal status, update `shipments`, insert `tracking_events`, publish Redis event, trigger notification.

**Status mapping**:
```
InTransit → in_transit
OutForDelivery → out_for_delivery
Delivered → delivered (triggers final installment activation + notification)
AttemptFail → delivery_attempted (triggers notification)
Exception → delivery_exception
Returned → returned (triggers refund workflow)
```

### POST /tracking/register
**Auth**: Internal  
**Body**: `{ order_id, tracking_number, courier_code }`  
**Logic**: Call AfterShip `POST /trackings`, store `aftership_tracking_id`.

### GET /tracking/{order_id}
**Auth**: Bearer  
**Response**: `{ courier, tracking_number, status, estimated_delivery, events: [{ time, description, location }] }`

### GET /admin/tracking/issues
**Auth**: Admin (operations_manager)  
**Response**: `{ orders: [{ order_id, customer, issue_type, days_overdue, action_buttons }] }`  
**Issue types**: `delivery_failed_2_attempts`, `returned_to_sender`, `customer_claims_not_received`, `exception`

---

# M11 — Ledger & Installment Engine

**Owner**: Qasim  
**Phase**: 3 | **Sprints**: S14–S15

---

## Purpose
Double-entry bookkeeping, daily billing sweep, late fee charity routing, TASDEEQ credit bureau reporting, payment reconciliation.

---

## Chart of Accounts (Seed Data)

```
ASSETS:   1001 Cash/Bank | 1100 AR-Installments | 1200 VCNs Issued
LIABILITY: 2001 AP-Merchants | 2100 Charity Payable | 2200 Customer Deposits
EQUITY:   3001 Owner Equity | 3900 Retained Earnings
REVENUE:  4001 Murabaha Profit | 4002 Affiliate Commission | 4003 Late Fee Collections
EXPENSE:  5001 COGS-Merchant Payment | 5002 Gateway Fees | 5003 VCN Issuance | 5004 Loan Loss Provision
```

---

## Database

```sql
ledger_accounts
  account_code VARCHAR(20) UNIQUE
  account_name, account_type CHECK ('asset','liability','equity','revenue','expense')
  normal_balance CHAR(6) CHECK ('debit','credit')

journal_entries
  entry_number VARCHAR(30) UNIQUE  -- JE-2025-0001234
  entry_date DATE, description TEXT
  entry_type CHECK ('payment_received','merchant_payment','refund','late_fee',
                    'charity_disbursement','provision','write_off','vcn_load','vcn_charge')
  source_type VARCHAR(30), source_id BIGINT  -- polymorphic
  is_balanced BOOLEAN DEFAULT FALSE           -- debits must = credits
  total_debit, total_credit DECIMAL(14,2)

journal_entry_lines
  journal_id, account_id
  debit_amount DECIMAL(14,2) DEFAULT 0
  credit_amount DECIMAL(14,2) DEFAULT 0
  -- CONSTRAINT: NOT (debit > 0 AND credit > 0) -- one side only
  -- CONSTRAINT: debit >= 0 AND credit >= 0

late_fee_charity_allocations
  installment_id, loan_id
  late_fee_amount DECIMAL(14,2)
  charity_org_id BIGINT
  allocated_at, disbursed_at, receipt_s3 VARCHAR(512)
  -- IMMUTABLE once disbursed
```

---

## Daily Billing Sweep (pg_cron: 0 8 * * *)

```sql
-- Uses CRITICAL partial index: installments(due_date, user_id) WHERE status='pending'
-- Processes 100K installments in < 60 seconds

SELECT i.*, u.phone, u.email
FROM installments i
JOIN users u ON u.id = i.user_id
WHERE i.status = 'pending'
AND i.due_date <= CURRENT_DATE
ORDER BY i.due_date ASC;
```

For each: attempt auto-debit (JazzCash/EasyPaisa direct API) → on success: mark PAID, create journal entry, TASDEEQ positive report → on failure: schedule retry.

---

## APIs

### GET /admin/finance/pl
**Auth**: Admin (finance_analyst)  
**Response**: `{ revenue: { murabaha_profit, affiliate_commission, consumer_fees, total }, costs: {...}, net_income, margin_pct }`

### GET /admin/finance/reconciliation
**Auth**: Admin  
**Response**: `{ gateways: [{ name, collected, fee, net_settlement, settlement_date, status }], discrepancies: [...] }`

### POST /admin/finance/reconciliation/import
**Auth**: Admin  
**Body**: Gateway settlement file (multipart)  
**Logic**: Match against `payment_transactions` by `gateway_txn_id`, flag discrepancies.

### GET /admin/finance/shariah-report
**Auth**: Admin (compliance_officer)  
**Query**: `?period=2026-Q1`  
**Response**: `{ murabaha_contracts_count, avg_markup_rate, ownership_transfer_pct, late_fees_collected, charity_disbursed, prohibited_items_blocked_count }`

---

# M12 — Admin Dashboard (20 Modules)

**Owner**: Minha (frontend) + Qasim (backend APIs)  
**Phase**: 3 | **Sprints**: S16–S18  
**All screens**: AD-01 through AD-28

---

## 20 Admin Modules

| # | Module | Priority | Role |
|---|---|---|---|
| AD-01 | Dashboard Home — KPI Command Center | Critical | All admins |
| AD-02 | User Management — List & Search | Critical | Ops Manager |
| AD-03 | User 360° Profile View | Critical | Ops/Risk/CS |
| AD-04 | Order Management — List | Critical | Ops Manager |
| AD-05 | Order Detail View | Critical | Ops Manager |
| AD-06 | HITL Queue | Critical | Ops Manager |
| AD-07 | Payment Operations — Collections | Critical | Finance |
| AD-08 | Payment Arrangement / Restructuring | High | Ops Manager |
| AD-09 | Risk & Fraud — Alert Queue | Critical | Fraud Analyst |
| AD-10 | Manual Underwriting Queue | High | Credit Analyst |
| AD-11 | Blacklist Management | High | Fraud Analyst |
| AD-12 | Financial Operations — P&L | High | Finance Analyst |
| AD-13 | Shariah Compliance Reports | High | Compliance Officer |
| AD-14 | Customer Support — Tickets | High | CS Agent |
| AD-15 | Ticket Detail Split View | High | CS Agent |
| AD-16 | KYC Manual Review Queue | High | Compliance Officer |
| AD-17 | Audit Trail Viewer | High | Compliance Officer |
| AD-18 | Regulatory Report Calendar | High | Compliance Officer |
| AD-19 | Analytics & BI — Executive | High | CEO/CFO |
| AD-20 | Conversion Funnel & Cohort | Medium | All |
| AD-21 | Custom Report Builder | Medium | All |
| AD-22 | Merchant & Partner Management | High | BD Lead |
| AD-23 | Team & Access Management | High | Super Admin |
| AD-24 | System Settings — Credit Policy | High | Ops Manager |
| AD-25 | System Health & Service Status | High | Tech |
| AD-26 | API & Developer Tools | Medium | Tech |
| AD-27 | Notification Center & Templates | Medium | Ops |
| AD-28 | Document Management — Contract Vault | Medium | Compliance |

---

## Key Admin APIs

### GET /admin/dashboard
**Auth**: Admin  
**Query**: `?date_range=30d`  
**Response**: 
```json
{
  "kpis": { "gmv", "active_users", "approval_rate", "default_rate", "revenue_month", "orders_today", "payments_due", "overdue_amount" },
  "charts": { "gmv_trend", "payment_status_donut", "order_funnel", "user_acquisition" },
  "action_items": [{ "priority", "type", "count", "action" }]
}
```
**Refresh**: every 60 seconds. All data from read replica.

### GET /admin/users
**Query**: `?search=ahmed&status=active&risk_band=D&page=1&limit=50`  
**Response**: `{ users: [...], total, page_info }`

### GET /admin/users/{id}
**Response**: Full 360 profile: personal, financial overview, orders, payments, activity log.

### GET /admin/analytics/dashboard
**Response**: Executive metrics with target vs actual: GMV growth, Revenue growth, CAC, LTV:CAC, Approval rate, Collection rate, Default rate, NPS.

### GET /admin/analytics/funnel
**Response**: Acquisition funnel + order completion funnel with conversion rates and drop-off at each stage.

### GET /admin/analytics/cohort
**Query**: `?type=retention|ltv&months=12`  
**Response**: Grid of cohort rows × months, values = % repeat purchase or cumulative PKR/user.

---

## Dashboard KPI Color Coding

- Green: ↑ positive trend or below threshold
- Yellow: approaching threshold — caution  
- Red: threshold breached — immediate action required

**Traffic light thresholds**:
- Default rate: Green < 1.5%, Yellow 1.5-2.5%, Red > 2.5%
- Collection rate: Green > 90%, Yellow 85-90%, Red < 85%
- Approval rate: Green > 70%, Yellow 65-70%, Red < 65%
- Fraud loss rate: Green < 0.2%, Yellow 0.2-0.3%, Red > 0.3%

---

## Materialized Views (nightly refresh)

```sql
mv_daily_revenue    -- GMV, gross profit, AOV per day
mv_loan_portfolio   -- status counts, outstanding totals, defaults
mv_merchant_performance  -- orders, GMV, checkout success rate per merchant
```
