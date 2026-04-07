# M05 — Shariah Contracts (Wakalah + Murabaha)
 
**Phase**: 1 | **Sprint**: S05 (Weeks 11–12)  
**Screens**: US-12 (Wakalah Signing), US-13 (Murabaha Signing)

---

## Purpose
Generate, display, and OTP-sign Wakalah (agency) and Murabaha (cost-plus sale) contracts. Enforce hard gate: VCN cannot issue without signed Murabaha.

---

## Two-Contract Structure (Agency Murabaha)

**Wakalah Agreement**: Customer appoints SahulatKar as Wakeel (agent) to purchase specific product from specific merchant at authorized amount. Signed first. Authorizes the purchase execution.

**Murabaha Contract**: SahulatKar sells the procured product to customer at cost + disclosed profit. Contains fixed installment schedule. Cannot be changed post-signing. Signed second. This is the HARD GATE.

**Legal basis**: SECP Islamic Finance Guidelines 2023, AAOIFI Shariah Standard No. 8, Federal Shariat Court precedents.

---

## HARD GATE

```python
# Gateway API middleware — enforced on EVERY request to POST /vcn/issue
if order.status != "contracts_signed":
    raise HTTPException(403, detail="MURABAHA_NOT_SIGNED")
```

This test runs in CI on every push. NEVER disable or mark as xfail.

---

## Database Tables

```sql
wakalah_agreements
  id, uuid
  contract_number VARCHAR(50) UNIQUE  -- SAK-WAK-2025-001234
  order_id BIGINT UNIQUE NOT NULL
  user_id BIGINT NOT NULL
  principal_name VARCHAR(200) NOT NULL   -- CNIC-verified legal name
  principal_cnic VARCHAR(20)             -- masked: 42101-XXXXXXX-1
  principal_phone VARCHAR(20) NOT NULL
  agent_name VARCHAR(100) DEFAULT 'SahulatKar (Pvt) Ltd.'
  agent_secp_license VARCHAR(50) NOT NULL
  product_description TEXT NOT NULL
  merchant_name VARCHAR(255) NOT NULL
  product_url VARCHAR(2048) NOT NULL
  authorized_amount DECIMAL(14,2) NOT NULL
  price_variance_pct DECIMAL(4,2) DEFAULT 5.00  -- agent can't exceed by > 5%
  contract_pdf_s3 VARCHAR(512) NOT NULL
  contract_hash VARCHAR(64) NOT NULL    -- SHA-256 integrity verification
  signed_via VARCHAR(20) DEFAULT 'otp'
  otp_reference VARCHAR(100)
  signed_at TIMESTAMP NOT NULL
  signing_ip INET, signing_device_id BIGINT
  valid_from TIMESTAMP, valid_until TIMESTAMP
  is_executed BOOLEAN DEFAULT FALSE
  executed_at TIMESTAMP

murabaha_contracts
  id, uuid
  contract_number VARCHAR(50) UNIQUE  -- SAK-MUR-2025-001234
  order_id BIGINT UNIQUE NOT NULL
  loan_id BIGINT UNIQUE REFERENCES loans(id)
  wakalah_id BIGINT REFERENCES wakalah_agreements(id)
  user_id BIGINT NOT NULL
  -- Mandatory Shariah disclosures (all NOT NULL — DB enforces Rule 2)
  cost_price DECIMAL(14,2) NOT NULL
  profit_amount DECIMAL(14,2) NOT NULL
  profit_rate_pct DECIMAL(5,2) NOT NULL
  total_repayable DECIMAL(14,2) NOT NULL
  currency CHAR(3) DEFAULT 'PKR'
  product_description TEXT NOT NULL
  payment_plan VARCHAR(20) NOT NULL
  installment_schedule JSONB NOT NULL
  contract_pdf_s3 VARCHAR(512) NOT NULL
  contract_hash VARCHAR(64) NOT NULL
  template_version VARCHAR(10) NOT NULL
  signed_via VARCHAR(20) DEFAULT 'otp'
  otp_reference VARCHAR(100)
  signed_at TIMESTAMP NOT NULL
  signing_ip INET
  validated_by_shariah_board BOOLEAN DEFAULT FALSE
  status CHECK ('active','completed','cancelled','disputed')

contract_digital_signatures
  id, contract_type VARCHAR(20)   -- 'wakalah','murabaha'
  contract_id BIGINT
  user_id BIGINT
  otp_hash VARCHAR(64)            -- SHA-256 of OTP used
  signed_at TIMESTAMP
  ip INET, user_agent TEXT
  verified_at TIMESTAMP
```

---

## APIs

### POST /contracts/wakalah/generate
**Auth**: Bearer  
**Body**: `{ order_id }`  
**Response**: `{ contract_id, contract_number, pdf_url, otp_sent: true }`  
**Logic**:
1. Fetch order + UPO + user details
2. Generate Wakalah PDF using ReportLab template
3. Upload to S3, store SHA-256 hash
4. Send OTP to user's phone
5. Create `wakalah_agreements` record with status pending signature

### POST /contracts/wakalah/sign
**Auth**: Bearer  
**Body**: `{ contract_id, otp_code }`  
**Response**: `{ signed: true, signed_at }`  
**Logic**: Verify OTP, set `signed_at`, update order status to `contracts_pending` (awaiting Murabaha). Log to `contract_digital_signatures`.

### POST /contracts/murabaha/generate
**Auth**: Bearer  
**Body**: `{ order_id, plan_type }` (only callable after Wakalah signed)  
**Response**: `{ contract_id, contract_number, pdf_url, financial_disclosure, otp_sent: true }`  
**Prerequisite**: `wakalah_agreements.is_executed = FALSE` AND `order.status = 'contracts_pending'`

### POST /contracts/murabaha/sign
**Auth**: Bearer  
**Body**: `{ contract_id, otp_code, confirmation_checkbox: true }`  
**Response**: `{ signed: true, signed_at, next_step: 'down_payment' }`  
**Logic**: Verify OTP + `confirmation_checkbox` must be true. Update order status to `contracts_signed`. This unlocks VCN issuance.  
**Errors**: `400 CONFIRMATION_REQUIRED`, `400 INVALID_OTP`, `409 ALREADY_SIGNED`

### GET /contracts/{order_id}
**Auth**: Bearer  
**Response**: `{ wakalah: { status, signed_at, pdf_url }, murabaha: { status, signed_at, pdf_url, financial_summary } }`

### GET /contracts/{contract_id}/pdf
**Auth**: Bearer (or admin)  
**Response**: Presigned S3 URL (valid 15 min) for PDF download

---

## Contract Templates (Key Clauses)

### Wakalah Template Required Fields
- Principal full name (CNIC-verified)
- Principal CNIC (masked in display, full in signed PDF)
- Agent: SahulatKar (Pvt) Ltd., SECP license number
- Product description and URL
- Authorized purchase amount
- Price variance tolerance: ±5%
- Wakalah fee: included in Murabaha markup
- Valid until: 24 hours from signing
- Legal basis: Electronic Transactions Ordinance 2002, Section 15

### Murabaha Template Required Fields (ALL MANDATORY — Shariah Rule 2)
- **Cost price** (merchant purchase price) — MUST be explicit PKR amount
- **Profit amount** (4% markup) — MUST be explicit PKR amount
- **Total repayable** — MUST be explicit PKR amount
- Full installment schedule with dates and amounts
- Ownership transfer clause: "upon physical delivery confirmation"
- Late fee: "PKR [amount] per late installment — 100% donated to Edhi Foundation — ZERO retained by SahulatKar"
- TASDEEQ reporting notice
- Shariah board certification reference

---

## PDF Generation (ReportLab)

```python
# Contract generation pipeline
def generate_murabaha_pdf(order, loan, user, plan):
    # 1. Fetch template (versioned — SSB certifies each version)
    template = load_template(f"murabaha_v{CURRENT_TEMPLATE_VERSION}")
    
    # 2. Validate all mandatory disclosures are non-null
    assert order.product_cost is not None
    assert loan.profit_amount is not None
    assert loan.profit_rate_pct is not None
    
    # 3. Generate PDF to BytesIO
    # 4. SHA-256 hash for integrity
    pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
    
    # 5. Upload to S3 with server-side encryption
    s3_key = f"contracts/murabaha/{order.id}/{contract_number}.pdf"
    
    # 6. Store hash in DB — verifiable anytime
    return s3_key, pdf_hash
```

---

## Shariah Advisory Board Requirements

- Minimum 1 SECP-recognized Shariah scholar
- Annual review and certification of both contract templates
- Certification stored in `shariah_board_approvals` table
- Contract template version bumped on any text change → requires new SSB certification
- Budget: PKR 200K-500K initial, PKR 100K-200K annual audit

---

## Signing States

```
WAKALAH:
  generated → otp_sent → signed → executed (when agent buys)
  
MURABAHA:
  generated (after Wakalah signed) → otp_sent → signed (HARD GATE UNLOCKED)
  → active (after down payment) → completed (all installments paid)
  → cancelled (pre-delivery) | disputed
  
HARD GATE: order.status = 'contracts_signed' is the ONLY state that permits VCN issuance
```
