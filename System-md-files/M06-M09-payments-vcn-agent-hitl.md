# M06 — Payment Orchestrator

**Phase**: 2 | **Sprint**: S07–S08  
**Screens**: US-14 (Down Payment), US-18 (Wallet), US-19 (Pay Installment)

---

## Purpose
Collect down payment, issue VCN, schedule installments, collect via JazzCash/EasyPaisa/Raast, reconcile with gateways.

---

## Payment Flow: COLLECT FIRST, THEN BUY

```
1. Order status = 'contracts_signed'
2. Present payment screen (amount, methods)
3. User pays down payment via Safepay/JazzCash/EasyPaisa
4. Webhook confirms payment → mark installment[0] as PAID
5. Publish 'payment.down_payment_confirmed' to Redis
6. VCN Service receives event → issues VCN
7. Checkout Agent receives VCN → executes purchase
```

NEVER execute purchase before down payment confirmed. NEVER issue VCN without confirmed payment.

---

## Payment Methods (Priority Order)

| Method | Users | Fee | Settlement |
|---|---|---|---|
| Safepay (cards + wallets) | Universal | 2.9% + PKR 30 | T+2 |
| JazzCash Direct API | 40M+ wallets | 1.5-2% | T+1 |
| EasyPaisa Direct API | 35M+ wallets | 1.5-2% | T+1 |
| Raast (Phase 4) | SBP instant | ~0% | T+0 |

**Operator detection**: After 4 digits of phone, show 'Jazz'/'Telenor'/'Zong'/'Ufone' badge. Show only methods available for that operator.

---

## Installment Retry Schedule

| Attempt | Time |
|---|---|
| 1 (due date) | 9:00 AM |
| 2 (same day) | 6:00 PM |
| 3 (next day) | 9:00 AM |
| 4 (day+2) | 12:00 PM |
| After 4 fails | Flag for manual collections outreach |

---

## Database Tables (key)

```sql
loans
  loan_number VARCHAR(30) UNIQUE  -- SAK-LOAN-2025-0001234
  user_id, order_id BIGINT UNIQUE, murabaha_contract_id
  principal_amount, profit_amount, total_repayable DECIMAL(14,2) NOT NULL
  down_payment_amount, balance_financed DECIMAL(14,2) NOT NULL
  profit_rate_pct DECIMAL(5,2) NOT NULL
  plan_type CHECK ('pay_in_3','pay_in_4','pay_in_6','pay_full')
  installment_count SMALLINT, installment_amount DECIMAL(14,2)
  status CHECK ('active','partially_paid','fully_paid','defaulted','written_off','disputed')
  total_paid, total_outstanding, late_fee_total DECIMAL(14,2)
  -- Triggers: fn_recalculate_available_credit() on UPDATE

installments
  loan_id, user_id, installment_number SMALLINT
  is_down_payment BOOLEAN DEFAULT FALSE
  principal_portion, profit_portion, total_amount DECIMAL(14,2)
  due_date DATE NOT NULL
  status CHECK ('pending','paid','overdue','defaulted','waived','rescheduled')
  paid_amount, paid_at
  days_overdue INTEGER DEFAULT 0
  late_fee_amount DECIMAL(14,2) DEFAULT 0  -- ALL goes to charity
  late_fee_waived BOOLEAN DEFAULT FALSE
  retry_count SMALLINT DEFAULT 0, next_retry_at TIMESTAMP
  -- CRITICAL INDEX: (due_date, user_id) WHERE status='pending'
  -- This is the daily billing sweep index — < 50ms for 100K rows

payment_transactions (PARTITIONED quarterly by created_at)
  installment_id, user_id, payment_method_id
  amount DECIMAL(14,2), currency CHAR(3) DEFAULT 'PKR'
  gateway CHECK ('safepay','jazzcash','easypaisa','raast','stripe','manual')
  gateway_txn_id VARCHAR(255) UNIQUE  -- Hash index for webhook lookup
  gateway_response JSONB
  status CHECK ('initiated','pending','success','failed','refunded','chargeback')
  failure_code, failure_message
  retry_of_txn_id BIGINT  -- self-reference for retry chain
  settlement_id BIGINT, reconciled_at TIMESTAMP
```

---

## APIs

### POST /payments/down-payment
**Auth**: Bearer  
**Body**: `{ order_id, method: 'safepay'|'jazzcash'|'easypaisa', amount_pkr }`  
**Response**: `{ payment_session_url }` (Safepay) OR `{ status: 'success', txn_id }` (JazzCash/EP direct)  
**Logic**: Create `payment_transactions` record, initiate gateway, return redirect URL or direct charge result.

### POST /webhooks/safepay
**Auth**: HMAC-SHA256 signature validation  
**Body**: Safepay event payload  
**Logic**: On `payment:created` + `state: PAID` → mark installment PAID → publish `payment.down_payment_confirmed` to Redis.

### POST /webhooks/jazzcash
**Auth**: HMAC signature  
**Logic**: On `pp_ResponseCode: "000"` → same as Safepay webhook handler.

### POST /payments/pay-installment
**Auth**: Bearer  
**Body**: `{ installment_id, method, payment_method_id? }`  
**Response**: `{ success, txn_id, paid_at, next_installment? }`

### GET /payments/schedule/{loan_id}
**Auth**: Bearer  
**Response**: `{ installments: [{ number, due_date, amount, status, late_fee?, paid_at? }] }`

### POST /payments/manual-record (admin — finance_analyst role)
**Body**: `{ user_id, installment_id, amount, payment_date, method, reference_number, proof_s3? }`  
**Logic**: Record manual payment (bank deposit, office cash), generate receipt to customer.

---

## Collections Escalation Timeline

| Day | Action | Channel |
|---|---|---|
| -7 | Pre-reminder | SMS + Push |
| -3 | Reminder | SMS + Email + Push |
| -1 | Final reminder | SMS + WhatsApp + Push |
| 0 | Due date auto-debit | JazzCash/EP API |
| +1 | Soft overdue | SMS + Push |
| +3 | Firm overdue + retry | SMS + IVR Call |
| +7 | Account restriction + human call | Call + SMS + App banner |
| +15 | No new purchases | SMS + Call + Legal warning |
| +30 | Formal notice + TASDEEQ negative report | Registered mail + SMS |
| +60 | Write-off review | Legal proceedings |

---

# M07 — VCN Issuance & Management

**Owner**: Qasim + Rayyan  
**Phase**: 2 | **Sprint**: S08

---

## Purpose
Issue single-use, MCC-locked, amount-capped virtual cards for automated checkout. Only after Murabaha signed + down payment confirmed.

---

## VCN Properties

- **Single-use**: Void automatically after first successful charge
- **Amount cap**: Product cost + 5% buffer (for tax/shipping variance)
- **MCC lock**: Only retail category codes allowed; cash advance, gambling blocked
- **Merchant lock**: Domain-specific lock in Lithic (Phase 2); MCC category in Stripe (MVP)
- **Expiry**: 24 hours from issuance — auto-void
- **Storage**: PAN + CVV AES-256 encrypted in DB; never logged in application logs

---

## Database

```sql
virtual_cards
  order_id BIGINT UNIQUE NOT NULL     -- 1:1 with order
  user_id BIGINT NOT NULL
  issuer VARCHAR(20) CHECK ('stripe','lithic','hbl_vcn')
  issuer_card_id VARCHAR(255) UNIQUE
  masked_number VARCHAR(19)           -- '**** **** **** 1234'
  card_expiry DATE
  authorized_amount DECIMAL(14,2)    -- product cost + 5%
  loaded_amount DECIMAL(14,2)        -- exact product cost
  mcc_lock VARCHAR(10)               -- MCC whitelist
  merchant_lock VARCHAR(255)         -- specific domain (Lithic only)
  charged_amount DECIMAL(14,2) DEFAULT 0
  is_used BOOLEAN DEFAULT FALSE, used_at TIMESTAMP
  status CHECK ('active','used','voided','expired','failed')
  voided_at, void_reason VARCHAR(100)
  issued_at, expires_at TIMESTAMP NOT NULL
```

---

## APIs

### POST /vcn/issue
**Auth**: Internal (Gateway → Payment Orchestrator)  
**Pre-check**: `order.status == "contracts_signed"` — else HTTP 403 MURABAHA_NOT_SIGNED  
**Body**: `{ order_id, amount_pkr, merchant_domain }`  
**Response**: `{ vcn_id, pan, expiry_month, expiry_year, cvv, status }`  
**Logic**: Call Stripe Issuing API with spending controls, store encrypted in DB, publish event.

### POST /vcn/void
**Auth**: Internal  
**Body**: `{ vcn_id, reason }`  
**Logic**: Call Stripe Issuing void endpoint, update `virtual_cards.status = 'voided'`.

### GET /vcn/{order_id}/status
**Auth**: Admin  
**Response**: `{ status, charged_amount, is_used, issued_at, expires_at }`

---

# M08 — Checkout Agent (Playwright)

**Owner**: Rayyan  
**Phase**: 2 | **Sprints**: S09–S10  
**Screen**: US-15 (Agent Executing)

---

## Purpose
Autonomous browser agent completes checkout on merchant website using VCN. Handles CAPTCHA, price changes, OOS, and self-healing via VLM.

---

## Checkout Steps

```
1. Dequeue job from BullMQ (priority 1)
2. Allocate Playwright pod (KEDA autoscaling 0→100)
3. Launch Chromium with stealth patches + BrightData residential proxy
4. Navigate to product page
5. Select correct variant (heuristic label matching)
6. Add to cart
7. Proceed to checkout
8. Detect + click "Guest Checkout"
9. Fill shipping form (heuristic field matching by label/placeholder/aria-label)
10. Switch to payment iframe (frame_locator)
11. Inject VCN: PAN, expiry, CVV with human-like typing delays (Gaussian ~100ms ±40ms)
12. Submit order
13. Screenshot + scrape confirmation page for merchant order ID
14. Verify via Stripe webhook that VCN was charged
15. Return { merchant_order_id, tracking_num, screenshot_s3 }
```

---

## Anti-Bot Stealth Stack

| Technique | Implementation |
|---|---|
| WebDriver flag removal | `navigator.webdriver = undefined` via init_script |
| Browser fingerprint | playwright-stealth + Canvas/WebGL/AudioContext randomization |
| Residential proxies | BrightData pool ($5/GB) |
| Bezier curve mouse | Custom JS: Bezier easing on page.mouse.move() |
| Human typing | page.keyboard.type() with Gaussian delay per character |
| CAPTCHA solving | 2Captcha ($1.50/1000) / CapSolver |
| Cookie persistence | browser.new_context(storage_state=...) |
| User-Agent rotation | Chrome 120 Windows realistic UAs |
| Timing variance | asyncio.sleep(random.uniform(0.5, 3.0)) between actions |
| Advanced Cloudflare | Patchright (drop-in replacement, patches CDP leaks) |

---

## Failure Modes & Resolution

| Failure | Frequency | Resolution |
|---|---|---|
| CAPTCHA | Medium | 2Captcha/CapSolver API → if fails → HITL |
| Out of stock | High | Notify user → alternative / cancel+refund |
| Price changed > 5% | Low | Pause → re-quote → user re-confirms |
| Bot detected / IP blocked | Medium | Retry with new proxy IP → HITL after 3 |
| Checkout error | Medium | HITL |
| VCN declined by merchant | Low | Reissue VCN with updated amount → retry |
| 3DS required | Low | HITL operator handles authentication |
| All retries exhausted | — | HITL queue with 15-min SLA |

---

## Self-Healing (VLM Recovery)

```python
async def self_heal(page, error_context):
    screenshot = await page.screenshot(type='jpeg', quality=70)
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": f"Error: {error_context}. What CSS selector should I click to proceed? Return ONLY the selector."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64encode(screenshot)}"}}
            ]
        }], max_tokens=100
    )
    selector = response.choices[0].message.content.strip()
    await page.click(selector, timeout=5000)
```

---

## Database

```sql
purchase_executions
  order_id BIGINT NOT NULL, vcn_id BIGINT
  attempt_number SMALLINT DEFAULT 1
  worker_id, proxy_used VARCHAR(100)
  status CHECK ('queued','running','succeeded','failed','hitl_escalated','cancelled')
  step_reached VARCHAR(50)
  failure_type CHECK ('captcha','site_down','price_changed','out_of_stock',
                      'cart_error','payment_declined','checkout_changed',
                      'bot_detected','timeout','unknown')
  error_detail TEXT, screenshot_s3 VARCHAR(512)
  merchant_order_id VARCHAR(255), merchant_order_url VARCHAR(2048)
  receipt_screenshot_s3 VARCHAR(512)
  duration_ms INTEGER, queued_at, started_at, completed_at TIMESTAMP
```

---

## APIs

### POST /agent/queue-job
**Auth**: Internal (called after VCN issued)  
**Body**: `{ order_id, vcn_id }`  
**Response**: `{ job_id, estimated_completion_seconds }`

### GET /agent/job/{job_id}/status (SSE stream)
**Auth**: Bearer  
**Response**: Server-sent events stream: `{ step, status, timestamp }` as each step completes

### POST /agent/job/{job_id}/cancel
**Auth**: Admin  
**Logic**: Cancel queued or running job, void VCN, initiate refund.

---

# M09 — HITL Queue & Ops Dashboard

**Owner**: Rayyan (backend) + Minha (admin frontend)  
**Phase**: 2 | **Sprint**: S11  
**Screen**: AD-06

---

## HITL SLA: 15 minutes from escalation

---

## Database

```sql
hitl_queue
  order_id BIGINT, execution_id BIGINT
  priority INT CHECK (1-5)         -- 1=highest (paid, large order)
  assigned_to BIGINT (admin_user)
  status CHECK ('pending','claimed','in_progress','resolved','cancelled')
  failure_reason TEXT, screenshot_s3 VARCHAR(512)
  resolution VARCHAR(100)
  resolved_at TIMESTAMP, sla_deadline TIMESTAMP
```

---

## APIs

### GET /admin/hitl
**Auth**: Admin (operations_manager)  
**Response**: `{ jobs: [{ order_id, customer, product, failure_type, time_in_queue_min, screenshot_url, priority }] }`  
**Logic**: Sorted by priority desc, then time_in_queue desc.

### POST /admin/hitl/{job_id}/claim
**Auth**: Admin  
**Logic**: Set `assigned_to = current_admin_id`, status = 'claimed'. Prevents duplicate work.

### POST /admin/hitl/{job_id}/resolve
**Auth**: Admin  
**Body**: `{ resolution: 'manual_purchase_completed'|'cancelled_refund'|'customer_contacted'|'alternative_offered', notes? }`  
**Logic**: Update HITL record, trigger downstream action (mark order confirmed or cancel+refund), log to `audit_trails`.

### POST /admin/hitl/{job_id}/open-browser
**Auth**: Admin  
**Response**: `{ remote_session_url }` — WebSocket URL to controlled browser session  
**Logic**: Operator takes over browser at the exact step where automation paused.
