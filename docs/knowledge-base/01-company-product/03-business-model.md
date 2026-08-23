# Business Model

**Status:** STABLE (figures sourced directly from `docs/System-md-files/00Sahulatkar-System.md` unit economics table and `M03-url-pipeline.md` pricing logic) · flags one open compliance item.

## Revenue streams

| Stream | Mechanism | Notes |
|---|---|---|
| Murabaha profit margin | Disclosed markup on cost price, tiered by plan length: 2.5% (pay-in-3), 4.0% (pay-in-4), 7.0% (pay-in-6) | **Compliance flag:** per `pricing_service.py:22`, this tiered structure has not yet received written Shariah board sign-off. Treat the 4% figure used elsewhere in these docs as the illustrative/reference rate, not a confirmed-compliant final structure. |
| Interchange-like economics | ~1.5% on the VCN transaction | Modeled in unit economics below |
| *(Not currently monetized)* Late fees | Calculated on overdue installments | 100% routed to charity (Edhi Foundation) — zero platform revenue by design, see [`../04-shariah/17-shariah-product-structure.md`](../04-shariah/17-shariah-product-structure.md) |

There is no merchant fee — SahulatKar has no merchant relationship to charge a fee against (see [`../02-business-workflows/06-merchant-vendor-journey.md`](../02-business-workflows/06-merchant-vendor-journey.md)). A `commission_rate` field exists on the `merchants` table for the small subset of tracked "affiliate partner" stores, but this is not confirmed as an active revenue stream in engineering documentation — flag as unconfirmed if referenced externally.

## Customer fees

None beyond the disclosed Murabaha profit margin baked into the repayment total. No separate "service fee" or membership fee is documented. Late fees exist as a mechanism but are not retained revenue (see above).

## Financing economics (worked example, PKR 10,000 order)

Sourced verbatim from the engineering quick-reference (`docs/System-md-files/00Sahulatkar-System.md`):

| Item | PKR |
|---|---|
| Murabaha Fee (4%) | +400 |
| Interchange (~1.5%) | +150 |
| **Total Revenue** | **+550** |
| Safepay (down payment) | −106 |
| JazzCash (3 installments) | −156 |
| Rye API (extraction) | −21 |
| Stripe VCN (issuance) | −28 |
| SMS + AfterShip + Infra | −26 |
| **Total Costs** | **−337** |
| **Net Contribution** | **+213** |
| **Break-even default rate** | **~1.9%** |

This is a single order at the reference 4% rate, not blended across plan types — the actual blended margin will differ once the 2.5%/4.0%/7.0% tiering is finalized and Shariah-approved.

## Settlement economics

SahulatKar pays the merchant in full at time of checkout (via the VCN) — there is no deferred merchant settlement, because there is no merchant relationship to settle against. What *is* reconciled is SahulatKar's own payment-gateway settlement: down payments and installments collected via Safepay (T+2) and JazzCash/EasyPaisa (T+1) against what actually lands in SahulatKar's bank account. See [`../02-business-workflows/11-merchant-settlement-reconciliation.md`](../02-business-workflows/11-merchant-settlement-reconciliation.md) — as of the last code audit this reconciliation runs against mock local files rather than live gateway APIs, a known gap.

## Operational costs

From the worked example: third-party extraction (Rye API, ~$0.02/fetch), OCR/liveness verification (Shufti Pro, ~$0.40–0.80/verification), VCN issuance (Stripe Issuing), CAPTCHA-solving (2Captcha/CapSolver, ~$1.50/1000), residential proxy bandwidth (BrightData, ~$5/GB), SMS/WhatsApp/push delivery, and AWS infrastructure (EKS/RDS/ElastiCache in `ap-south-1`). Human-in-the-loop operations (KYC manual review, checkout HITL escalation, collections calling) are a real but not yet quantified operational cost — no documented cost-per-HITL-resolution figure exists in current engineering docs.

## Partner costs

Payment gateway fees (Safepay 2.9% + PKR 30 per transaction; JazzCash/EasyPaisa 1.5–2%), NADRA/TASDEEQ integration costs (not separately quantified in engineering docs), and the Shariah Advisory Board (budgeted PKR 200K–500K initial setup, PKR 100K–200K annual audit, per `M05-contracts.md`).

## Default/loss assumptions

Credit-band structure targets thin-file, cold-start-capped exposure (see [`../03-bnpl-financing/15-credit-limit-rules.md`](../03-bnpl-financing/15-credit-limit-rules.md)) specifically to manage default risk before a user has a repayment track record. The single hard unit-economics number in engineering docs is the **break-even default rate of ~1.9%** on the reference 10,000 PKR order above; no broader portfolio-level default-rate target or loss-provisioning policy is documented elsewhere in the repo as of this writing — this is a gap worth closing with Finance/Risk before launch.

## Open items for Finance/Product to resolve

1. Confirm final, Shariah-board-approved markup structure (flat vs. tiered) before this document's revenue figures are treated as final.
2. Document a portfolio-level default rate target and loss-provisioning policy (currently only the single-order break-even figure exists).
3. Confirm whether merchant "affiliate partner" commissions are an active or planned revenue stream.
