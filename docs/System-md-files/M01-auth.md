# M01 — Auth & Identity Core
 
**Phase**: 1 | **Sprint**: S01 (Weeks 3-4)  
**Screens**: US-02 (Phone Register), US-03 (OTP Verify)

---

## Purpose
JWT authentication, phone OTP, RBAC, MFA for admin, session management. Everything else depends on this.

---

## Database Tables

```sql
-- users (core identity, see CLAUDE.md for full schema)
-- Key fields:
id BIGSERIAL PRIMARY KEY
uuid UUID UNIQUE DEFAULT gen_random_uuid()
phone VARCHAR(20) UNIQUE NOT NULL  -- E.164 +92XXXXXXXXXX
password_hash VARCHAR(255)         -- bcrypt cost=12
status VARCHAR(20) DEFAULT 'pending_kyc'
  CHECK (status IN ('pending_kyc','active','suspended','closed','blocked'))
failed_login_attempts SMALLINT DEFAULT 0
locked_until TIMESTAMP

-- admin_users
id BIGSERIAL PRIMARY KEY
email VARCHAR(255) UNIQUE NOT NULL
mfa_secret_encrypted BYTEA        -- AES-256
mfa_enabled BOOLEAN DEFAULT TRUE
force_password_change BOOLEAN DEFAULT FALSE

-- user_sessions
id BIGSERIAL PRIMARY KEY
user_id BIGINT REFERENCES users(id)
access_token_hash VARCHAR(64)     -- SHA-256
refresh_token_hash VARCHAR(64)
device_id BIGINT
ip INET
expires_at TIMESTAMP
revoked_at TIMESTAMP
```

---

## APIs

### POST /auth/register/initiate
**Auth**: None  
**Body**: `{ phone, first_name, last_name, email?, referral_code? }`  
**Response**: `{ otp_token, masked_phone }`  
**Logic**: Validate E.164 format, check not duplicate in `users(phone)` WHERE deleted_at IS NULL, send OTP via Jazz SMS API, store OTP hash in Redis with 3-min TTL.  
**Errors**: `409 PHONE_ALREADY_REGISTERED`, `422 INVALID_PHONE_FORMAT`

### POST /auth/verify-otp
**Auth**: None  
**Body**: `{ otp_token, otp_code }`  
**Response**: `{ access_token, refresh_token, user_id, kyc_status }`  
**Logic**: Compare OTP hash in Redis, max 3 attempts then lock 5 min, issue JWT (15-min access + 24-hr refresh), store session in Redis.  
**Errors**: `400 INVALID_OTP`, `400 OTP_EXPIRED`, `429 TOO_MANY_ATTEMPTS`

### POST /auth/login
**Auth**: None  
**Body**: `{ phone, otp_code }` (OTP login) or `{ phone, password }`  
**Response**: `{ access_token, refresh_token, user_id, kyc_status }`

### POST /auth/refresh
**Auth**: Bearer refresh_token  
**Response**: `{ access_token }` (new 15-min token)

### POST /auth/logout
**Auth**: Bearer access_token  
**Logic**: Revoke session in Redis + DB `user_sessions.revoked_at = NOW()`

### POST /auth/otp/resend
**Auth**: None  
**Body**: `{ otp_token }`  
**Logic**: Only after countdown expiry. Rate-limited: 3 resends/hr per phone.

### POST /admin/auth/login
**Auth**: None  
**Body**: `{ email, password, totp_code }`  
**Response**: `{ access_token, admin_id, role }`  
**Logic**: TOTP mandatory for all admin. bcrypt verify + pyotp.TOTP.verify. Session TTL 2hr (configurable per role).

### GET /auth/me
**Auth**: Bearer access_token  
**Response**: `{ user_id, uuid, phone, kyc_status, credit_limit, available_credit, status }`

---

## Redis Keys

| Key | TTL | Value |
|---|---|---|
| `otp:{phone}:{type}` | 180s | hashed OTP code |
| `otp:attempts:{phone}` | 300s | attempt count |
| `session:{token_hash}` | 86400s | user_id + session_id |
| `admin:session:{token_hash}` | 28800s | admin_id + role |

---

## RBAC Roles

| Role | Key Permissions |
|---|---|
| super_admin | All modules, all actions |
| operations_manager | Users, Orders, Payments, Support, Reports |
| credit_risk_analyst | Risk module, User profiles (financial only) |
| fraud_analyst | Risk/Fraud, Blacklist — read-only elsewhere |
| cs_agent | Tickets, User profiles (read-only), Order status |
| finance_analyst | Financial Ops, Reconciliation — no PII, no order edit |
| compliance_officer | Compliance, KYC queue, Audit trails — no account modify |
| marketing_manager | Marketing, Analytics (non-PII) — no financial/user data |

**Field-level examples**: CS agents can VIEW KYC status but CANNOT view raw CNIC number. Finance analysts can VIEW all payments but CANNOT mark as received.

---

## Security Rules

- JWT access token: 15-min expiry, RS256 signed
- Refresh token: 24-hr, rotation on each use
- Admin TOTP: mandatory, no fallback to SMS
- Concurrent sessions: 1 per customer, new login terminates old
- Inactivity timeout: 2hr admin (configurable), none for customer
- IP allowlist: finance + super_admin roles (office IP only)
- Password: bcrypt cost=12
- MFA secret: AES-256 encrypted in DB

---

## States

**User account**: `pending_kyc` → `active` → `suspended` | `closed` | `blocked`  
**Session**: active → revoked (logout/new login/timeout)  
**OTP**: sent → verified | expired | max_attempts_exceeded
