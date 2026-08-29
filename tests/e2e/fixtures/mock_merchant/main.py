"""
Mock merchant site for the SahulatKar end-to-end workflow test.

This is a throwaway fixture, not a real merchant. It exists so the E2E suite
can drive the ACTUAL extraction pipeline (html_scraper.py's JSON-LD parse)
and the ACTUAL Playwright checkout automation (form_filler.py) against a
deterministic, offline, zero-cost target instead of a real e-commerce site or
a mocked-out extraction/checkout layer.

Design constraints, derived directly from reading the two real consumers:

- apps/product-service/src/extractors/html_scraper.py::extract_json_ld
  requires a <script type="application/ld+json"> block with "@type": "Product",
  a "name", and "offers".{"price", "priceCurrency", "availability"} (schema.org
  URL form, e.g. "https://schema.org/InStock").

- apps/product-service/src/services/checkout/form_filler.py::run_checkout
  drives a real Chromium browser through, in order: navigate -> click
  "Add to Cart"/"Buy Now" -> read a cart total from a `[data-total]`-ish
  element or "PKR/Rs <amount>" text -> click "Guest Checkout"/"Checkout as
  Guest" -> type into input[name*=email/firstname/lastname/address1/city/
  phone] -> optionally click a shipping radio -> type into
  input[name*=cardnumber/exp/cvv] (no iframe) -> optionally click
  "Review"/"Continue" -> click "Place Order"/"Complete Purchase" -> expect
  page text/URL containing one of "order confirmed"/"thank you"/"order #"/
  "/thank-you"/"/order-confirmed"/"/success".

Every page below is real server-rendered HTML with real <form> navigation
(GET/POST), not client-side JS, so Playwright's normal navigation/waiting
model applies exactly as it would against a real site.

No card data received here is ever logged in full or persisted beyond the
in-memory submission record used for the E2E test's own assertions (last 4
digits + total only) — this container never leaves the docker-compose test
network and never talks to a real payment network, but it costs nothing to
keep the same "never log full PAN" discipline used in the real services.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(title="SahulatKar E2E Mock Merchant")

# item_id -> catalog entry. Price is deliberately a round PKR figure with no
# fractional component so downstream percentage math (down payment %, profit
# rate %) in the real services produces clean, easy-to-assert numbers.
CATALOG: dict[str, dict] = {
    "widget-1": {
        "name": "SahulatKar E2E Test Widget",
        "price": "12000.00",
        "currency": "PKR",
        "description": "A deterministic fixture product used only by the SahulatKar end-to-end test suite.",
        "image": "https://e2e-mock-merchant.invalid/widget-1.jpg",
    },
    "widget-price-drift": {
        "name": "SahulatKar E2E Price-Drift Widget",
        "price": "12000.00",
        "currency": "PKR",
        "description": "Same fixture as widget-1, but its cart page quotes a drastically higher "
        "total than the listing price -- deliberately exceeds "
        "product-service's PRICE_DRIFT_THRESHOLD_PCT (5%) so form_filler.py's "
        "price-drift check raises PRICE_MISMATCH at checkout, driving the "
        "PurchaseExecution to hitl_escalated. Used only by "
        "test_admin_workflows.py to exercise the real HITL queue end-to-end.",
        "image": "https://e2e-mock-merchant.invalid/widget-price-drift.jpg",
        "cart_price": "20000.00",  # >5% drift from the listing price above
    },
}

# In-memory submission log, keyed by a server-generated merchant order id.
# Cleared on container restart -- fine, the E2E suite owns the container's
# lifecycle for the duration of a single test run.
_SUBMISSIONS: dict[str, dict] = {}


def _catalog_entry(item_id: str) -> dict:
    entry = CATALOG.get(item_id)
    if entry is None:
        raise KeyError(item_id)
    return entry


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "e2e-mock-merchant"}


@app.get("/product/{item_id}", response_class=HTMLResponse)
async def product_page(item_id: str) -> str:
    entry = _catalog_entry(item_id)
    return f"""<!doctype html>
<html>
<head>
<title>{entry['name']}</title>
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "{entry['name']}",
  "description": "{entry['description']}",
  "image": "{entry['image']}",
  "offers": {{
    "@type": "Offer",
    "price": "{entry['price']}",
    "priceCurrency": "{entry['currency']}",
    "availability": "https://schema.org/InStock"
  }}
}}
</script>
</head>
<body>
  <h1>{entry['name']}</h1>
  <p class="price">PKR {entry['price']}</p>
  <p>{entry['description']}</p>
  <form method="get" action="/cart/{item_id}">
    <button type="submit">Add to Cart</button>
  </form>
</body>
</html>"""


@app.get("/cart/{item_id}", response_class=HTMLResponse)
async def cart_page(item_id: str) -> str:
    entry = _catalog_entry(item_id)
    cart_total = entry.get("cart_price", entry["price"])
    return f"""<!doctype html>
<html>
<head><title>Your Cart</title></head>
<body>
  <h1>Cart</h1>
  <div class="cart-line">{entry['name']} x 1</div>
  <div class="price-final" data-total="{cart_total}">Total: PKR {cart_total}</div>
  <form method="get" action="/checkout/{item_id}">
    <button type="submit">Checkout as Guest</button>
  </form>
</body>
</html>"""


@app.get("/checkout/{item_id}", response_class=HTMLResponse)
async def checkout_page(item_id: str) -> str:
    _catalog_entry(item_id)
    return f"""<!doctype html>
<html>
<head><title>Checkout</title></head>
<body>
  <h1>Checkout</h1>
  <form method="post" action="/checkout/{item_id}/submit">
    <input name="email" type="email" placeholder="Email" />
    <input name="firstname" type="text" placeholder="First name" />
    <input name="lastname" type="text" placeholder="Last name" />
    <input name="address1" type="text" placeholder="Address" />
    <input name="city" type="text" placeholder="City" />
    <input name="phone" type="tel" placeholder="Phone" />

    <label><input type="radio" name="shipping" value="standard" checked /> Standard shipping</label>
    <label><input type="radio" name="shipping" value="express" /> Express shipping</label>

    <input name="cardnumber" type="text" placeholder="Card number" />
    <input name="exp" type="text" placeholder="MM/YY" />
    <input name="cvv" type="text" placeholder="CVV" />

    <button type="button" onclick="this.style.display='none'; document.getElementById('place-order').style.display='inline';">Review</button>
    <button id="place-order" type="submit">Place Order</button>
  </form>
</body>
</html>"""


@app.post("/checkout/{item_id}/submit", response_class=HTMLResponse)
async def checkout_submit(
    item_id: str,
    email: str = Form(...),
    firstname: str = Form(...),
    lastname: str = Form(...),
    address1: str = Form(...),
    city: str = Form(...),
    phone: str = Form(...),
    shipping: str = Form("standard"),
    cardnumber: str = Form(...),
    exp: str = Form(...),
    cvv: str = Form(...),
) -> str:
    entry = _catalog_entry(item_id)
    merchant_order_id = f"SK-E2E-{uuid.uuid4().hex[:10].upper()}"
    _SUBMISSIONS[merchant_order_id] = {
        "item_id": item_id,
        "email": email,
        "firstname": firstname,
        "lastname": lastname,
        "address1": address1,
        "city": city,
        "phone": phone,
        "shipping": shipping,
        "card_last4": cardnumber[-4:] if len(cardnumber) >= 4 else cardnumber,
        "total": entry["price"],
    }
    return f"""<!doctype html>
<html>
<head><title>Order Confirmed</title></head>
<body>
  <h1>Thank you!</h1>
  <p>Order confirmed. Order # {merchant_order_id}</p>
  <div class="confirmation-number">{merchant_order_id}</div>
</body>
</html>"""


class SubmissionOut(BaseModel):
    item_id: str
    email: str
    firstname: str
    lastname: str
    address1: str
    city: str
    phone: str
    shipping: str
    card_last4: str
    total: str


@app.get("/_debug/submissions/{merchant_order_id}", response_model=Optional[SubmissionOut])
async def debug_get_submission(merchant_order_id: str):
    return _SUBMISSIONS.get(merchant_order_id)


@app.get("/_debug/submissions", response_model=dict[str, SubmissionOut])
async def debug_list_submissions():
    return _SUBMISSIONS


@app.post("/_debug/reset")
async def debug_reset():
    _SUBMISSIONS.clear()
    return {"status": "ok"}
