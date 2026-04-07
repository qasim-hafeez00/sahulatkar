# M03 — URL Pipeline & Product Service

**Phase**: 1 | **Sprint**: S06 (Weeks 13–14)  
**Screens**: US-10 (Extraction Loading), US-11 (Product Preview)

---

## Purpose
Receive any product URL → normalize → detect platform → extract product data via waterfall → return Universal Product Object (UPO) → present financing offer.

---

## Extraction Waterfall

| Tier | Method | Trigger | Cost | Speed |
|---|---|---|---|---|
| 1 | Rye API v2 | Amazon + Shopify URLs, or any URL | $0.02/fetch | < 5s |
| 2 | JSON-LD / schema.org | Any site — try before browser | Free | < 2s |
| 3 | Playwright + Groq LLM | JS-heavy or schema-less | $0.05–0.15 proxy | 15–60s |
| 4 | HITL (manual) | All automation failed | $1.50–2.00 BPO | < 15 min |

---

## URL Processing Steps

```python
1. Receive raw input (paste or Share Sheet)
2. Expand shortened URLs (bit.ly, amzn.to) → follow HTTP 301/302
3. Strip tracking params (utm_source, ref, affid, fbclid, etc.)
4. Validate URL → HTTP 200 (else: product not found)
5. Detect platform from URL pattern:
   - amazon.*/dp/{ASIN}         → AMAZON
   - store.com/products/{handle} → SHOPIFY
   - daraz.pk/products/...       → DARAZ
   - /product/ path              → WOOCOMMERCE_LIKELY
   - else                        → CUSTOM
6. Classify: Product Page | Category Page | Non-Product
   - Non-product → HTTP 422 NOT_A_PRODUCT_URL
7. Prohibited category check → HTTP 422 PROHIBITED_CATEGORY
8. Try extraction waterfall until success
9. Validate UPO (price > 0, title not empty, availability known)
10. Store in DB + return to frontend
```

---

## Universal Product Object (UPO) Schema

```typescript
interface UPO {
  product_id: string           // uuid
  source_url: string           // canonical, tracking-stripped
  platform: string             // AMAZON|SHOPIFY|DARAZ|CUSTOM
  extraction_method: string    // rye_api|json_ld|playwright_llm|hitl
  extracted_at: string         // ISO8601
  meta: {
    title: string
    brand: string
    description: string        // max 500 chars
    images: Array<{ url, is_featured, alt_text }>
  }
  pricing: {
    amount: number             // in paisas
    currency: string           // PKR
    display_price: string      // "Rs. 12,500"
    tax_inclusive: boolean
    original_price?: number
  }
  availability: 'in_stock'|'out_of_stock'|'preorder'|'backorder'|'unknown'
  is_purchasable: boolean
  variants: Array<{
    option_name: string        // "Size"|"Color"
    options: Array<{ label, value, is_available }>
  }>
  shipping: {
    estimated_cost: number
    estimated_days: string
    ships_to_pakistan: boolean
  }
  financing: {                 // computed by backend
    loan_amount: number
    service_fee: number        // 4%
    down_payment: number
    installments: Array<{ number, amount, due_date }>
  }
}
```

---

## Database Tables

```sql
products
  id, uuid, canonical_url TEXT, merchant_id BIGINT
  platform VARCHAR(30)
  title TEXT NOT NULL, title_urdu TEXT
  current_price DECIMAL(14,2), currency CHAR(3) DEFAULT 'PKR'
  is_available BOOLEAN DEFAULT TRUE
  stock_status VARCHAR(20) CHECK ('in_stock','out_of_stock','limited','unknown')
  primary_image_s3 VARCHAR(512)   -- cached to prevent broken links in contracts
  is_prohibited BOOLEAN DEFAULT FALSE
  prohibition_reason VARCHAR(100)
  search_vector TSVECTOR          -- GIN index for full-text search
  extraction_confidence DECIMAL(4,3)
  extraction_method VARCHAR(30)

scraping_jobs (PARTITIONED monthly by created_at)
  id, uuid, order_id, user_id, product_id
  input_url TEXT, canonical_url TEXT
  platform_detected, status VARCHAR(20)
    CHECK ('queued','running','completed','failed','retrying','cancelled')
  attempt_number SMALLINT DEFAULT 1, max_attempts SMALLINT DEFAULT 3
  result JSONB                    -- raw UPO from extraction
  error_code, error_message, duration_ms
  queued_at, started_at, completed_at

prohibited_categories
  id, category_name VARCHAR(100)
  keywords TEXT[]                 -- matched against product title/description
  shariah_basis TEXT
  added_by BIGINT, created_at

merchants
  id, uuid, name, domain VARCHAR(255) UNIQUE
  platform_type, checkout_success_rate DECIMAL(5,2)
  has_captcha BOOLEAN, captcha_type VARCHAR(30)
  bot_detection_level VARCHAR(20) CHECK ('none','low','medium','high','extreme')
  status VARCHAR(20) CHECK ('active','degraded','blocked','monitoring')
  scrape_config JSONB             -- CSS selectors, XPath overrides per merchant
  is_affiliate_partner BOOLEAN DEFAULT FALSE
  commission_rate DECIMAL(5,4)
```

---

## APIs

### POST /products/extract
**Auth**: Bearer (customer)  
**Body**: `{ raw_url: string }`  
**Response**: `{ upo_id, upo: UPO, financing_offer }` or `{ status: 'extracting', job_id }`  
**Logic**:
1. URL normalization pipeline
2. Prohibited check → 422 if blocked
3. Rye API (if Shopify/Amazon) → if success, return UPO
4. JSON-LD extraction → if found, return UPO
5. Playwright + LLM job queued → return `{ status: 'extracting', job_id }`
6. Client polls `GET /products/jobs/{job_id}`  
**Errors**: `422 NOT_A_PRODUCT_URL`, `422 PROHIBITED_CATEGORY`, `422 OUT_OF_STOCK`, `422 DOES_NOT_SHIP_TO_PAKISTAN`, `404 PRODUCT_NOT_FOUND`

### GET /products/jobs/{job_id}
**Auth**: Bearer  
**Response**: `{ status: 'queued'|'running'|'completed'|'failed', upo?, error? }`  
**Usage**: Frontend polls every 3s during US-10 loading screen.

### GET /products/{upo_id}/offer
**Auth**: Bearer  
**Response**: `{ product: UPO, variants, plans: [...], murabaha_pricing, credit_check: { available_credit, order_amount, sufficient: bool } }`  
**Logic**: Compute Murabaha pricing for each available plan. Check user's available_credit against order amount.

### GET /products/search
**Auth**: Bearer  
**Query**: `?q=nike+shoes&limit=20`  
**Response**: `{ products: UPO[] }`  
**Logic**: GIN full-text search on `search_vector` (English) and `search_vector_urdu`.

---

## Murabaha Pricing Calculation

```python
MARKUP_RATES = {
  'pay_in_3': 0.025,   # 2.5%
  'pay_in_4': 0.040,   # 4.0%
  'pay_in_6': 0.070,   # 7.0%
}

def calculate_schedule(product_cost_pkr, shipping_pkr, plan_type):
    cost = product_cost_pkr + shipping_pkr
    markup = round(cost * MARKUP_RATES[plan_type])
    total = cost + markup
    # Equal installments, last adjusted for rounding
    # MANDATORY DISCLOSURE: cost_price, profit_amount, total — all three
```

---

## Prohibited Categories (Shariah Rule 3)

Blocked at extraction stage, before any financing offer:
- Alcohol and alcohol-related products
- Tobacco and nicotine products
- Gambling, lottery, games of chance
- Interest-bearing financial instruments
- Adult content and entertainment
- Non-halal food products (where identifiable)
- Weapons and ammunition (consumer market)

All blocks logged to `prohibited_items_log` (immutable, append-only).

---

## URL Pattern Reference

| Platform | URL Pattern | Extraction Tier |
|---|---|---|
| Amazon | amazon.com/dp/{ASIN} | Tier 1: Rye API |
| Shopify | store.com/products/{handle} | Tier 1: Rye API |
| Daraz | daraz.pk/products/{slug}-{id}.html | Tier 3: Playwright |
| WooCommerce | store.com/product/{slug}/ | Tier 2: JSON-LD |
| AliExpress | aliexpress.com/item/{id}.html | Tier 3: Playwright |
| Custom | Any other | Tier 3: Playwright + LLM |
