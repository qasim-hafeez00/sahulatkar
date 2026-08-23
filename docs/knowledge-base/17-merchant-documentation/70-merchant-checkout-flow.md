# Merchant Checkout Flow (from the merchant site's perspective)

**Status:** STABLE — this is the one merchant-documentation-category topic that genuinely has rich technical detail, since the checkout agent's interaction with a merchant site is a core, real piece of the platform. See [`../05-architecture/microservices/product-service.md`](../05-architecture/microservices/product-service.md) for the owning service.

## What the merchant site "sees"

From the merchant website's own perspective, a SahulatKar-driven purchase looks like an ordinary guest checkout by an individual consumer:

1. A browser session (Chromium, stealth-patched, residential-proxy-routed) lands on the product page.
2. The correct variant is selected via heuristic label matching.
3. Item added to cart, guest checkout selected.
4. Shipping form filled via heuristic field matching (label/placeholder/aria-label).
5. Payment iframe (if present) is switched into, and card details are entered — PAN/expiry/CVV from the single-use VCN — with human-like typing delays.
6. Order submitted; confirmation page scraped for the merchant's own order ID.

Full technical detail: [`../05-architecture/microservices/product-service.md`](../05-architecture/microservices/product-service.md), `docs/System-md-files/M06-M09-payments-vcn-agent-hitl.md` (M08 section).

## Anti-bot considerations (relevant specifically because there is no merchant cooperation)

Because the merchant site has no reason to expect or welcome automated purchasing, the checkout agent is built to look as close to an ordinary human shopper as reasonably possible: WebDriver-flag removal, canvas/WebGL/audio fingerprint randomization, residential IPs, Bezier-curve mouse movement, Gaussian-distributed typing delays, and CAPTCHA-solving fallback (2Captcha/CapSolver). This is a direct consequence of the vendor-agnostic model — a cooperating merchant integration wouldn't need any of this.

## Known critical gap

**The payment-form-filling step (entering the VCN details) and order-confirmation detection are currently an incomplete stub** (`PS-BL-03`) — no automated checkout can currently complete end-to-end. This document describes the intended flow; see [`../05-architecture/microservices/product-service.md`](../05-architecture/microservices/product-service.md) for the current implementation status.

## What happens when the merchant site blocks this

CAPTCHA unsolvable, bot detected, IP blocked, or 3DS required → escalates to the HITL queue (15-minute SLA), where a human operator either completes the checkout manually or cancels/refunds the order. See [`../05-architecture/microservices/product-service.md`](../05-architecture/microservices/product-service.md) failure-mode table.

## Related documents

[`65-merchant-overview.md`](65-merchant-overview.md), [`71-merchant-order-flow.md`](71-merchant-order-flow.md), [`../05-architecture/microservices/product-service.md`](../05-architecture/microservices/product-service.md).
