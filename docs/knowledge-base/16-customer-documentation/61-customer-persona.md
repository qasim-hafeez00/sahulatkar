# Customer Persona

**Status:** STABLE (inferred from product design decisions) — no formal user-research persona document exists in current engineering docs; this persona is reconstructed from what the product's own design choices imply about its intended user, and should be validated against real research if/when Product/Growth conducts it.

## Primary persona (inferred)

**"Thin-file digital shopper"** — a Pakistani consumer, phone-first, who:

- Has a working CNIC and a registered mobile number, but likely no formal credit bureau history (the entire alternative-data credit engine design — device signals, telco data, behavioral velocity — exists specifically because this persona can't be underwritten conventionally, see [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md)).
- Shops across a wide range of online stores, not just a few large platforms — implied by the vendor-agnostic "any URL" design, rather than a curated marketplace.
- Is comfortable with mobile wallets (JazzCash/EasyPaisa) as much as or more than cards — implied by those being prioritized alongside Safepay in the payment method list, and by the phone-operator-detection UX feature.
- Cares about the product being interest-free/Shariah-compliant — implied by the product's entire positioning, not an optional feature.
- Has modest order sizes relative to conventional credit products — implied by the cold-start caps (PKR 2,000–8,000 for a first order) and the Band D default profile (PKR 3,000 limit, 33% down payment).

## Age and eligibility

18+ is a hard requirement (Layer 1 hard block). No upper age bound is documented.

## Income

Minimum monthly income requirement defaults to PKR 30,000 (configurable range PKR 20K–50K) — see [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md). This puts the primary persona in a lower-to-middle income bracket relative to Pakistan's income distribution, consistent with a thin-file/first-time-financing-product profile.

## Shopping behavior

Likely price-sensitive on individual items (electronics, apparel, appliances are the categories with explicit risk-tuning in the Credit Engine's Layer 6 — see [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md)) but willing to pay a modest markup (2.5–7%) to spread payment over weeks rather than paying in full immediately.

## Financial needs

Access to short-term, small-ticket financing without a credit history requirement, without interest (for religious/values reasons or general interest-aversion), and without needing the specific store they want to buy from to have any BNPL integration.

## Pain points (inferred from the product's design responses to them)

- Locked out of conventional credit due to no bureau history → addressed by alternative-data underwriting.
- Wants Shariah-compliant financing, not widely available for online-shopping use cases → addressed by the Wakalah/Murabaha structure.
- Wants to buy from a specific store that doesn't offer any BNPL option → addressed by the vendor-agnostic URL model.

## Technology usage

Comfortable using a mobile app for OTP-based authentication, document photo capture (CNIC, selfie), and mobile-wallet payments — a moderately tech-comfortable but not necessarily desktop-first user, consistent with the Next.js mobile-responsive customer app design.

## Caveat

**This entire document is inferred from product/engineering design decisions, not from user research.** Product/Growth should replace this with an actual research-backed persona (interviews, survey data, early-cohort analysis) as soon as real user data exists — treat this as a placeholder that at least won't contradict the product's own design logic, not as validated market research.

## Related documents

[`62-customer-lifecycle.md`](62-customer-lifecycle.md), [`../01-company-product/01-product-overview.md`](../01-company-product/01-product-overview.md).
